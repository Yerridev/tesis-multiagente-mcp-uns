"""
Servidor MCP SOLO LECTURA del modulo de caudal MCC-09 (laboratorio USS).  v1.0

Expone a un agente de IA el historiador del UNS (TimescaleDB) mediante herramientas controladas.
- Se conecta con el rol mcp_lector (solo SELECT) y ademas abre cada sesion en modo read-only.
- No tiene ninguna ruta hacia el PLC: no puede escribir consignas, salidas ni registros.
- Cada respuesta incluye unidad, periodo, fuente y advertencias; si no hay datos lo dice.

Instalacion (en la laptop, dentro del venv):
    pip install -r mcp_servidor/requirements.txt
Prueba manual:
    set MCP_DSN=postgresql://mcp_lector:TU_CLAVE@localhost:5432/uns
    python mcp_servidor/servidor_mcp.py --probar
Uso normal: lo lanza el cliente MCP (Claude Desktop, OpenCode...) por stdio. Ver README.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError  # su mensaje si llega al agente
from mcp.types import ToolAnnotations

DSN = os.getenv("MCP_DSN", "postgresql://mcp_lector:lector_cambiar@localhost:5432/uns")
BASE = os.getenv("UNS_BASE", "uss/campus/lab-automatizacion/sl01la07/caudal-mcc09")
HEARTBEAT_MAX_S = float(os.getenv("HEARTBEAT_MAX_S", "30"))   # el conector late cada 10 s
VALOR_MAX_S = float(os.getenv("VALOR_MAX_S", "90"))           # el conector republica cada 60 s aunque no cambie
TZ_LIMA = timezone(timedelta(hours=-5))
VARIABLE_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)+$")
MAX_MINUTOS = 60 * 24 * 31
SOLO_LECTURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

INSTRUCCIONES = """Servidor de SOLO LECTURA del modulo de control de caudal MCC-09 (PLC Siemens S7-200 CPU226,
laboratorio de automatizacion USS). Datos del Unified Namespace guardados en TimescaleDB.
Reglas para el agente:
- Nunca inventes valores, unidades ni limites: usa solo lo que devuelven las herramientas.
- Siempre menciona unidad, hora o periodo consultado y si el dato esta VIGENTE o DESACTUALIZADO.
- Si una herramienta devuelve advertencias (rango no validado, sin datos, modo LOCAL...), comunicalas.
- No puedes modificar el proceso. Si te piden cambiar el setpoint o arrancar/parar, explica que el sistema es solo lectura.
Contexto del proceso: en modo REMOTO el PID regula el caudal moviendo el variador de la bomba;
en modo LOCAL manda el potenciometro del tablero. 'caudal/pv_pid' es el caudal visto por el PID y
'caudal/caudalimetro' es la lectura directa del caudalimetro (solo en REMOTO); deberian coincidir.
Para preguntas de por que el caudal no sigue al setpoint usa primero diagnosticar_lazo; consultar_grafo
describe los equipos y sus relaciones causales."""

mcp = MCPServer("caudal-mcc09", instructions=INSTRUCCIONES, version="1.3")


# ----------------------------------------------------------------------------- utilidades
def _conectar() -> psycopg.Connection:
    try:
        return psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5,
                               options="-c default_transaction_read_only=on -c statement_timeout=8000")
    except psycopg.OperationalError as e:
        raise ToolError("No se puede conectar al historiador (TimescaleDB). Verifica que Docker este corriendo "
                        f"(docker compose up -d). Detalle: {str(e).strip()[:200]}") from e


def _consulta(sql: str, params: tuple | dict = ()) -> list[dict]:
    with _conectar() as con, con.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(TZ_LIMA).isoformat(timespec="seconds") if t else None


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _num(x: Any, nd: int = 3) -> float | None:
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else round(x, nd)


def _validar_variable(variable: str) -> str:
    variable = (variable or "").strip().strip("/")
    if variable.startswith(BASE):
        variable = variable[len(BASE):].strip("/").removeprefix("funcional/")
    if not VARIABLE_RE.match(variable):
        raise ToolError(f"Nombre de variable no valido: '{variable}'. Usa listar_variables para ver los nombres.")
    existe = _consulta("SELECT 1 FROM variables WHERE variable = %s UNION ALL "
                       "SELECT 1 FROM mediciones WHERE variable = %s LIMIT 1", (variable, variable))
    if not existe:
        raise ToolError(f"La variable '{variable}' no existe en el historiador. Usa listar_variables.")
    return variable


def _periodo(minutos: float | None, inicio: str | None, fin: str | None) -> tuple[datetime, datetime]:
    def parse(s: str) -> datetime:
        try:
            t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"Fecha no valida: '{s}'. Usa ISO 8601, p. ej. 2026-10-19T14:30") from None
        return t if t.tzinfo else t.replace(tzinfo=TZ_LIMA)

    if inicio:
        t0 = parse(inicio)
        t1 = parse(fin) if fin else (t0 + timedelta(minutes=minutos) if minutos else _ahora())
    else:
        m = 60 if minutos is None else float(minutos)
        if not 0 < m <= MAX_MINUTOS:
            raise ToolError(f"minutos debe estar entre 1 y {MAX_MINUTOS}")
        t1 = parse(fin) if fin else _ahora()
        t0 = t1 - timedelta(minutes=m)
    if t1 <= t0:
        raise ToolError("El fin del periodo debe ser posterior al inicio")
    if (t1 - t0) > timedelta(days=366 * 4):
        raise ToolError("Periodo demasiado largo (maximo 4 anios)")
    return t0, t1


def _validar_fuente(fuente: str) -> str:
    if fuente not in ("uns", "lvm"):
        raise ToolError("fuente debe ser 'uns' (en vivo) o 'lvm' (historicos 2008-2011 del SCADA original)")
    return fuente


def _estado_enlace() -> dict:
    """Estado del conector edge y del PLC a partir de los mensajes de texto del UNS."""
    filas = _consulta(
        """SELECT DISTINCT ON (topic) topic, texto, time FROM eventos
           WHERE topic IN (%(e)s, %(p)s, %(h)s) ORDER BY topic, time DESC""",
        {"e": f"{BASE}/funcional/edge/estado", "p": f"{BASE}/funcional/plc/conexion",
         "h": f"{BASE}/funcional/edge/heartbeat"})
    d = {f["topic"].rsplit("/", 2)[-2] + "/" + f["topic"].rsplit("/", 1)[-1]: f for f in filas}
    edge, plc, hb = d.get("edge/estado"), d.get("plc/conexion"), d.get("edge/heartbeat")
    edad_hb = (_ahora() - hb["time"]).total_seconds() if hb else None
    ok = bool(edge and edge["texto"] == "ONLINE" and plc and plc["texto"] == "CONECTADO"
              and edad_hb is not None and edad_hb <= HEARTBEAT_MAX_S)
    motivos = []
    if not edge or edge["texto"] != "ONLINE":
        motivos.append(f"conector edge {edge['texto'] if edge else 'sin reportar'}")
    if not plc or plc["texto"] != "CONECTADO":
        motivos.append(f"PLC {plc['texto'] if plc else 'sin reportar'}")
    if edad_hb is None or edad_hb > HEARTBEAT_MAX_S:
        motivos.append("sin latido reciente del conector" + (f" (hace {edad_hb:.0f} s)" if edad_hb else ""))
    return {
        "datos_en_vivo": ok,
        "conector_edge": edge["texto"] if edge else None,
        "conexion_plc": plc["texto"] if plc else None,
        "ultimo_latido": _iso(hb["time"]) if hb else None,
        "segundos_desde_latido": _num(edad_hb, 1),
        "motivos": motivos,
    }


def _ultimos(variables: list[str]) -> dict[str, dict]:
    filas = _consulta(
        """SELECT DISTINCT ON (m.variable) m.variable, m.valor, m.unidad, m.time, m.direccion, v.descripcion
           FROM mediciones m LEFT JOIN variables v USING (variable)
           WHERE m.fuente = 'uns' AND m.variable = ANY(%s)
           ORDER BY m.variable, m.time DESC""", (variables,))
    return {f["variable"]: f for f in filas}


def _modo_actual() -> dict:
    u = _ultimos(["estado/selector_remoto", "estado/selector_local", "estado/modo_hmi_pc",
                  "estado/sistema_funcionando", "estado/nivel_alto", "estado/nivel_bajo"])

    def b(k):
        return None if k not in u else bool(u[k]["valor"])

    remoto, local = b("estado/selector_remoto"), b("estado/selector_local")
    modo = "REMOTO" if remoto else "LOCAL" if local else "DESCONOCIDO" if remoto is None else "NINGUNO (selector en 0)"
    return {
        "modo": modo,
        "mando": None if b("estado/modo_hmi_pc") is None else ("HMI" if b("estado/modo_hmi_pc") else "PC"),
        "sistema_funcionando": b("estado/sistema_funcionando"),
        "nivel_alto": b("estado/nivel_alto"),
        "nivel_bajo": b("estado/nivel_bajo"),
    }


def _estadisticas(variable: str, fuente: str, t0: datetime, t1: datetime) -> dict:
    f = _consulta(
        """SELECT count(*) AS n, avg(valor) AS promedio, min(valor) AS minimo, max(valor) AS maximo,
                  stddev_samp(valor) AS desviacion, min(time) AS primero, max(time) AS ultimo,
                  (array_agg(valor ORDER BY time))[1] AS valor_inicial,
                  (array_agg(valor ORDER BY time DESC))[1] AS valor_final,
                  max(unidad) AS unidad
           FROM mediciones WHERE variable = %s AND fuente = %s AND time >= %s AND time < %s""",
        (variable, fuente, t0, t1))[0]
    return f


# Empareja dos variables en intervalos de 10 s tomando el ULTIMO valor de cada una al final del intervalo
# (muestreo y retencion; "b" no puede ser mas viejo que :retencion s). Devuelve tambien cuanto vario "a"
# dentro del intervalo (rango_a, para descartar transitorios) y si la bomba estaba en marcha.
# Necesario porque el conector solo publica por cambio: un setpoint estable aparece una vez por minuto.
_SQL_PAREADO = """
WITH a AS (
    SELECT date_bin('10 seconds', time, %(t0)s) AS t, max(valor) - min(valor) AS rango_a
    FROM mediciones WHERE fuente = 'uns' AND variable = %(a)s AND time >= %(t0)s AND time < %(t1)s
    GROUP BY 1)
SELECT a.t, a.rango_a, pa.valor AS va, pb.valor AS vb, ps.valor AS bomba
FROM a
CROSS JOIN LATERAL (
    SELECT valor FROM mediciones
    WHERE fuente = 'uns' AND variable = %(a)s AND time < a.t + interval '10 seconds'
    ORDER BY time DESC LIMIT 1) pa
CROSS JOIN LATERAL (
    SELECT valor FROM mediciones
    WHERE fuente = 'uns' AND variable = %(b)s AND time < a.t + interval '10 seconds'
      AND time >= a.t + interval '10 seconds' - make_interval(secs => %(retencion)s)
    ORDER BY time DESC LIMIT 1) pb
LEFT JOIN LATERAL (
    SELECT valor FROM mediciones
    WHERE fuente = 'uns' AND variable = 'estado/sistema_funcionando' AND time < a.t + interval '10 seconds'
    ORDER BY time DESC LIMIT 1) ps ON true
ORDER BY a.t"""


def _desv(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# ----------------------------------------------------------------------------- herramientas
@mcp.tool(annotations=SOLO_LECTURA)
def listar_variables() -> dict:
    """Lista las variables del modulo de caudal disponibles en el historiador (nombre UNS, direccion en el PLC,
    unidad, descripcion) con su ultimo dato en vivo y cuantos datos historicos (.lvm 2008-2011) tiene."""
    filas = _consulta(
        """WITH u AS (SELECT DISTINCT ON (variable) variable, time FROM mediciones
                      WHERE fuente = 'uns' ORDER BY variable, time DESC),
                h AS (SELECT variable, count(*) AS n FROM mediciones WHERE fuente = 'lvm' GROUP BY variable),
                todas AS (SELECT variable FROM variables UNION SELECT variable FROM u UNION SELECT variable FROM h)
           SELECT t.variable, v.tag_plc, v.direccion, v.unidad, v.descripcion,
                  u.time AS ultimo_dato_vivo, coalesce(h.n, 0) AS muestras_historicas
           FROM todas t LEFT JOIN variables v USING (variable) LEFT JOIN u USING (variable) LEFT JOIN h USING (variable)
           ORDER BY t.variable""")
    return {
        "base_uns": f"{BASE}/funcional/",
        "variables": [{**f, "ultimo_dato_vivo": _iso(f["ultimo_dato_vivo"])} for f in filas],
        "nota": "Los nombres se usan tal cual en las demas herramientas (p. ej. 'caudal/pv_pid').",
    }


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_lectura(variables: list[str]) -> dict:
    """Devuelve el ultimo valor en vivo de una o varias variables (maximo 20), con unidad, hora,
    antiguedad en segundos y si esta VIGENTE o DESACTUALIZADO. Ejemplo: ["caudal/pv_pid", "caudal/setpoint"]."""
    if isinstance(variables, str):
        variables = [variables]
    if not variables or len(variables) > 20:
        raise ToolError("Indica entre 1 y 20 variables")
    nombres = [_validar_variable(v) for v in variables]
    enlace = _estado_enlace()
    modo = _modo_actual()
    ult = _ultimos(nombres)
    ahora = _ahora()
    salida = []
    for n in nombres:
        f = ult.get(n)
        if not f:
            salida.append({"variable": n, "estado": "SIN_DATOS", "motivo": "nunca se recibio un dato en vivo"})
            continue
        edad = (ahora - f["time"]).total_seconds()
        estado, motivo = "VIGENTE", None
        if not enlace["datos_en_vivo"]:
            estado, motivo = "DESACTUALIZADO", "; ".join(enlace["motivos"])
        elif edad > VALOR_MAX_S:
            estado = "DESACTUALIZADO"
            if n in ("caudal/caudalimetro", "caudal/caudalimetro_raw") and modo["modo"] != "REMOTO":
                motivo = f"solo se publica en modo REMOTO; el modo actual es {modo['modo']}"
            elif n == "actuadores/potenciometro" and modo["modo"] != "LOCAL":
                motivo = f"solo se publica en modo LOCAL; el modo actual es {modo['modo']}"
            else:
                motivo = f"sin actualizacion hace {edad:.0f} s (se espera al menos cada {VALOR_MAX_S:.0f} s)"
        salida.append({"variable": n, "valor": _num(f["valor"], 4), "unidad": f["unidad"], "hora": _iso(f["time"]),
                       "antiguedad_s": _num(edad, 1), "estado": estado, "motivo": motivo,
                       "direccion_plc": f["direccion"], "descripcion": f["descripcion"]})
    return {"consultado": _iso(ahora), "enlace": enlace, "modo": modo["modo"], "lecturas": salida}


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_estado_plc() -> dict:
    """Estado general del sistema: conexion del conector edge y del PLC, ultimo latido, modo de operacion
    (REMOTO/LOCAL), origen del mando (PC/HMI), bomba en marcha y alarmas de nivel del tanque."""
    enlace = _estado_enlace()
    modo = _modo_actual()
    u = _ultimos(["caudal/pv_pid", "caudal/setpoint_pid", "actuadores/variador_pct", "actuadores/valvula_pct"])
    resumen = {k: {"valor": _num(f["valor"], 2), "unidad": f["unidad"], "hora": _iso(f["time"])} for k, f in u.items()}
    advertencias = list(enlace["motivos"])
    if modo["nivel_bajo"]:
        advertencias.append("ALARMA: nivel bajo en el tanque")
    if modo["nivel_alto"]:
        advertencias.append("Indicador de nivel alto activo")
    return {"consultado": _iso(_ahora()), "enlace": enlace, **modo, "resumen_proceso": resumen,
            "advertencias": advertencias}


@mcp.tool(annotations=SOLO_LECTURA)
def consultar_historial(variable: str, minutos: float | None = 60, inicio: str | None = None,
                        fin: str | None = None, fuente: str = "uns", puntos_max: int = 60) -> dict:
    """Historial de una variable en un periodo: estadisticas (promedio, minimo, maximo, desviacion, valor
    inicial y final, variacion) y una serie resumida de hasta 'puntos_max' puntos (promedio por intervalo).
    Periodo: los ultimos 'minutos' (por defecto 60) o 'inicio'/'fin' en ISO 8601 (hora de Lima si no tiene zona).
    fuente='uns' para datos en vivo o 'lvm' para los historicos 2008-2011 del SCADA original."""
    variable = _validar_variable(variable)
    fuente = _validar_fuente(fuente)
    t0, t1 = _periodo(minutos, inicio, fin)
    puntos_max = max(5, min(int(puntos_max), 500))
    st = _estadisticas(variable, fuente, t0, t1)
    resp = {"variable": variable, "fuente": fuente, "periodo": {"inicio": _iso(t0), "fin": _iso(t1)},
            "unidad": st["unidad"], "muestras": st["n"], "advertencias": []}
    if not st["n"]:
        resp["advertencias"].append("No hay datos en ese periodo")
        ultimo = _consulta("SELECT max(time) AS t FROM mediciones WHERE variable = %s AND fuente = %s",
                           (variable, fuente))[0]["t"]
        resp["ultimo_dato_disponible"] = _iso(ultimo)
        return resp
    paso = max(1, math.ceil((t1 - t0).total_seconds() / puntos_max))
    serie = _consulta(
        """SELECT date_bin(make_interval(secs => %s), time, %s) AS t, avg(valor) AS v, min(valor) AS mn, max(valor) AS mx
           FROM mediciones WHERE variable = %s AND fuente = %s AND time >= %s AND time < %s
           GROUP BY 1 ORDER BY 1""", (paso, t0, variable, fuente, t0, t1))
    resp.update({
        "estadisticas": {
            "promedio": _num(st["promedio"]), "minimo": _num(st["minimo"]), "maximo": _num(st["maximo"]),
            "desviacion": _num(st["desviacion"]), "valor_inicial": _num(st["valor_inicial"]),
            "valor_final": _num(st["valor_final"]),
            "variacion": _num(st["valor_final"] - st["valor_inicial"]),
            "primer_dato": _iso(st["primero"]), "ultimo_dato": _iso(st["ultimo"]),
        },
        "intervalo_serie_s": paso,
        "serie": [{"t": _iso(f["t"]), "promedio": _num(f["v"]), "min": _num(f["mn"]), "max": _num(f["mx"])}
                  for f in serie],
    })
    if fuente == "uns":
        resp["advertencias"].append("El conector publica por cambio (banda muerta) o cada 60 s: las muestras no son "
                                    "equiespaciadas y el promedio no esta ponderado por tiempo.")
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def comparar_con_rango(variable: str = "caudal/pv_pid", minutos: float = 5) -> dict:
    """Compara el valor actual y los ultimos 'minutos' de una variable con su rango validado por el responsable
    del laboratorio: dice si esta dentro, que porcentaje de muestras quedo fuera y si el rango aun no fue validado."""
    variable = _validar_variable(variable)
    t0, t1 = _periodo(minutos, None, None)
    rango = _consulta("SELECT minimo, maximo, unidad, validado_por, nota, actualizado FROM rangos_validados "
                      "WHERE variable = %s", (variable,))
    lectura = obtener_lectura([variable])
    actual = lectura["lecturas"][0]
    resp = {"variable": variable, "periodo": {"inicio": _iso(t0), "fin": _iso(t1)}, "lectura_actual": actual,
            "advertencias": []}
    if not rango:
        resp["advertencias"].append("Esta variable no tiene rango registrado; no se puede evaluar.")
        return resp
    r = rango[0]
    resp["rango"] = {"minimo": r["minimo"], "maximo": r["maximo"], "unidad": r["unidad"],
                     "validado_por": r["validado_por"], "nota": r["nota"]}
    if (r["validado_por"] or "").upper() == "PENDIENTE":
        resp["advertencias"].append("RANGO PROVISIONAL: aun no lo valida el responsable del laboratorio.")
    st = _consulta(
        """SELECT count(*) AS n, count(*) FILTER (WHERE valor < %s OR valor > %s) AS fuera,
                  avg(valor) AS promedio, min(valor) AS minimo, max(valor) AS maximo
           FROM mediciones WHERE variable = %s AND fuente = 'uns' AND time >= %s AND time < %s""",
        (r["minimo"], r["maximo"], variable, t0, t1))[0]
    resp["periodo_stats"] = {"muestras": st["n"], "fuera_de_rango": st["fuera"],
                             "porcentaje_fuera": _num(100 * st["fuera"] / st["n"], 1) if st["n"] else None,
                             "promedio": _num(st["promedio"]), "minimo": _num(st["minimo"]),
                             "maximo": _num(st["maximo"])}
    v = actual.get("valor")
    if v is None:
        resp["evaluacion"] = "SIN_DATO_ACTUAL"
    else:
        resp["evaluacion"] = "DENTRO" if r["minimo"] <= v <= r["maximo"] else "FUERA"
    if actual.get("estado") != "VIGENTE":
        resp["advertencias"].append(f"La lectura actual esta {actual.get('estado')}: {actual.get('motivo')}")
    if not st["n"]:
        resp["advertencias"].append("Sin muestras en el periodo indicado")
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def verificar_coherencia_caudal(minutos: float = 10, tolerancia_lpm: float = 3.0) -> dict:
    """Regla de diagnostico: compara el caudal que ve el PID (caudal/pv_pid) con la lectura directa del
    caudalimetro (caudal/caudalimetro, solo en modo REMOTO), en intervalos de 10 s. Si difieren mas que
    'tolerancia_lpm' indica posible problema de escalado, de calibracion o del sensor."""
    t0, t1 = _periodo(minutos, None, None)
    filas = _consulta(_SQL_PAREADO, {"a": "caudal/pv_pid", "b": "caudal/caudalimetro", "t0": t0, "t1": t1,
                                     "retencion": VALOR_MAX_S})
    todas = [{"t": f["t"], "pid": f["va"], "caudalimetro": f["vb"], "diferencia": f["va"] - f["vb"],
              "transitorio": f["rango_a"] is not None and f["rango_a"] > tolerancia_lpm} for f in filas]
    filas = [f for f in todas if not f["transitorio"]]
    n_trans = len(todas) - len(filas)
    resp = {"periodo": {"inicio": _iso(t0), "fin": _iso(t1)}, "unidad": "L/min",
            "tolerancia_lpm": tolerancia_lpm, "advertencias": []}
    if n_trans:
        resp["intervalos_transitorios_excluidos"] = n_trans
        resp["advertencias"].append(f"Se excluyeron {n_trans} intervalos con el caudal cambiando mas de "
                                    f"{tolerancia_lpm} L/min en 10 s (arranques, paradas o cambios de setpoint).")
    if not filas:
        modo = _modo_actual()["modo"]
        resp["evaluacion"] = "SIN_DATOS"
        resp["advertencias"].append("No hay intervalos estables con ambas medidas. El caudalimetro no se publica "
                                    f"en modo LOCAL (modo actual: {modo}).")
        return resp
    if max(abs(float(f["pid"])) for f in filas) < 1.0 and max(abs(float(f["caudalimetro"])) for f in filas) < 1.0:
        resp["advertencias"].append("Ambas medidas estan cerca de 0 L/min (bomba detenida): la coherencia solo es "
                                    "significativa con caudal circulando.")
    dif = [float(f["diferencia"]) for f in filas]
    fuera = [f for f in filas if abs(float(f["diferencia"])) > tolerancia_lpm]
    media = sum(dif) / len(dif)
    resp.update({
        "intervalos_comparados": len(filas),
        "diferencia_media": _num(media), "diferencia_max_abs": _num(max(abs(d) for d in dif)),
        "intervalos_fuera_tolerancia": len(fuera),
        "evaluacion": "COHERENTE" if not fuera else "INCOHERENTE",
        "ejemplos_fuera": [{"t": _iso(f["t"]), "pid": _num(f["pid"]), "caudalimetro": _num(f["caudalimetro"])}
                           for f in fuera[:5]],
    })
    if fuera and abs(media) > tolerancia_lpm:
        resp["interpretacion"] = ("Diferencia sistematica: revisar el escalado (140 L/min de fondo en el PID frente a "
                                  "141 L/min de la calibracion) o la calibracion del caudalimetro.")
    elif fuera:
        resp["interpretacion"] = "Diferencias puntuales en regimen estable: revisar el sensor o el cableado de AIW0."
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def comparar_con_historico_lvm(minutos: float = 10, tolerancia_setpoint_lpm: float = 5.0) -> dict:
    """Compara el desempenio actual del lazo (error caudal - setpoint, variabilidad) con los registros historicos
    del SCADA original (2008-2011) que operaron con un setpoint parecido (+- tolerancia)."""
    t0, t1 = _periodo(minutos, None, None)
    pares = _consulta(_SQL_PAREADO, {"a": "caudal/pv_pid", "b": "caudal/setpoint_pid", "t0": t0, "t1": t1,
                                     "retencion": VALOR_MAX_S})
    detenido = sum(1 for f in pares if f["bomba"] is not None and f["bomba"] < 0.5)
    pares = [f for f in pares if f["bomba"] is None or f["bomba"] >= 0.5]
    n_trans = sum(1 for f in pares if f["rango_a"] is not None and f["rango_a"] > 3.0)
    pares = [f for f in pares if f["rango_a"] is None or f["rango_a"] <= 3.0]   # solo regimen estable
    if detenido:
        resp_detenido = f"Se excluyeron {detenido} intervalos con la bomba detenida."
    actual = {"n": len(pares)}
    if pares:
        pv = [f["va"] for f in pares]
        err = [f["va"] - f["vb"] for f in pares]
        actual.update({"sp": sum(f["vb"] for f in pares) / len(pares), "pv": sum(pv) / len(pv),
                       "error_medio": sum(err) / len(err), "error_abs_medio": sum(abs(e) for e in err) / len(err),
                       "desviacion_pv": _desv(pv)})
    resp = {"periodo_actual": {"inicio": _iso(t0), "fin": _iso(t1)}, "unidad": "L/min", "advertencias": []}
    if detenido:
        resp["advertencias"].append(resp_detenido)
    if n_trans:
        resp["advertencias"].append(f"Se excluyeron {n_trans} intervalos transitorios (el caudal vario mas de 3 L/min "
                                    "en 10 s): se compara solo el regimen estable.")
    if not actual["n"]:
        resp["evaluacion"] = "PROCESO_DETENIDO" if detenido else "SIN_DATOS_ACTUALES"
        resp["advertencias"].append("No hay intervalos con la bomba en marcha en el periodo" if detenido
                                    else "No hay datos en vivo de caudal y setpoint en el periodo")
        return resp
    sp = float(actual["sp"])
    if sp < 1.0:
        resp["evaluacion"] = "PROCESO_DETENIDO"
        resp["advertencias"].append(f"Setpoint medio {sp:.2f} L/min: el lazo no esta regulando caudal, no hay nada "
                                    "que comparar con el historico. Pon el modulo en REMOTO con un setpoint.")
        return resp
    hist = _consulta(
        """SELECT count(*) AS n, count(DISTINCT p.direccion) AS archivos, min(p.time) AS desde, max(p.time) AS hasta,
                  avg(p.valor - s.valor) AS error_medio, avg(abs(p.valor - s.valor)) AS error_abs_medio,
                  stddev_samp(p.valor) AS desviacion_pv
           FROM mediciones p JOIN mediciones s
             ON s.time = p.time AND s.fuente = 'lvm' AND s.variable = 'caudal/setpoint'
           WHERE p.fuente = 'lvm' AND p.variable = 'caudal/pv_pid' AND abs(s.valor - %s) <= %s""",
        (sp, tolerancia_setpoint_lpm))[0]
    resp["actual"] = {"intervalos_10s": actual["n"], "setpoint_medio": _num(sp), "caudal_medio": _num(actual["pv"]),
                      "error_medio": _num(actual["error_medio"]), "error_abs_medio": _num(actual["error_abs_medio"]),
                      "desviacion_caudal": _num(actual["desviacion_pv"])}
    if not hist["n"]:
        resp["evaluacion"] = "SIN_REFERENCIA_HISTORICA"
        resp["advertencias"].append(f"No hay registros .lvm con setpoint entre {sp - tolerancia_setpoint_lpm:.1f} y "
                                    f"{sp + tolerancia_setpoint_lpm:.1f} L/min")
        return resp
    resp["historico_lvm"] = {"muestras": hist["n"], "archivos": hist["archivos"], "desde": _iso(hist["desde"]),
                             "hasta": _iso(hist["hasta"]), "error_medio": _num(hist["error_medio"]),
                             "error_abs_medio": _num(hist["error_abs_medio"]),
                             "desviacion_caudal": _num(hist["desviacion_pv"])}
    ea, eh = actual["error_abs_medio"], hist["error_abs_medio"]
    if ea is not None and eh:
        r = float(ea) / float(eh)
        resp["relacion_error_actual_vs_historico"] = _num(r, 2)
        resp["evaluacion"] = ("SIMILAR AL HISTORICO" if 0.67 <= r <= 1.5 else
                              "MEJOR QUE EL HISTORICO" if r < 0.67 else "PEOR QUE EL HISTORICO")
    resp["advertencias"].append("El mapa de canales de los .lvm se infirio de los datos; confirmalo antes de "
                                "sacar conclusiones fuertes.")
    return resp


# ----------------------------------------------------------------------------- conocimiento + diagnostico
GRAFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento", "grafo_mcc09.json")
TOL_ERROR_LPM = float(os.getenv("TOL_ERROR_LPM", "1.5"))     # error aceptable en regimen estable
TOL_SENSOR_LPM = float(os.getenv("TOL_SENSOR_LPM", "3.0"))   # diferencia aceptable PV del PID vs caudalimetro
VENTANA_DIAG_S = 30                                          # ventana de evaluacion del regimen


def _grafo() -> dict:
    with open(GRAFO_PATH, encoding="utf-8") as f:
        return json.load(f)


def _cadena(g: dict, pares: list[tuple[str, str]]) -> list[str]:
    """Traduce una lista de (origen, destino) a frases del grafo: 'variador --acciona--> bomba'."""
    out = []
    for de, a in pares:
        r = next((r for r in g["relaciones"] if r["de"] == de and r["a"] == a), None)
        if r:
            out.append(f"{g['nodos'][de]['nombre']} --{r['rel']}--> {g['nodos'][a]['nombre']}"
                       + (f"  ({r['nota']})" if r.get("nota") else ""))
    return out


def _aristas(g: dict, pares: list[tuple[str, str]]) -> list[dict]:
    """Misma cadena que _cadena pero estructurada (para resaltarla en el lienzo visual)."""
    out = []
    for de, a in pares:
        r = next((r for r in g["relaciones"] if r["de"] == de and r["a"] == a), None)
        if r:
            out.append({"de": de, "a": a, "rel": r["rel"]})
    return out


def _ventana(variables: list[str], segundos: float, t_ref: datetime | None = None) -> dict[str, dict]:
    """Por variable: ultimo valor, y min/max/promedio en la ventana incluyendo el valor vigente al inicio
    (necesario porque el conector solo publica por cambio)."""
    filas = _consulta(
        """WITH v AS (SELECT unnest(%(vars)s::text[]) AS variable),
                ini AS (SELECT DISTINCT ON (m.variable) m.variable, m.valor FROM mediciones m JOIN v USING (variable)
                        WHERE m.fuente = 'uns' AND m.time <= %(tr)s - make_interval(secs => %(s)s)
                          AND m.time > %(tr)s - interval '2 hours'
                        ORDER BY m.variable, m.time DESC),
                win AS (SELECT m.variable, m.valor, m.time FROM mediciones m JOIN v USING (variable)
                        WHERE m.fuente = 'uns' AND m.time > %(tr)s - make_interval(secs => %(s)s)
                          AND m.time <= %(tr)s),
                todo AS (SELECT variable, valor FROM ini UNION ALL SELECT variable, valor FROM win),
                ult AS (SELECT DISTINCT ON (m.variable) m.variable, m.valor AS ultimo, m.time AS t_ultimo
                        FROM mediciones m JOIN v USING (variable)
                        WHERE m.fuente = 'uns' AND m.time > %(tr)s - interval '2 hours' AND m.time <= %(tr)s
                        ORDER BY m.variable, m.time DESC)
           SELECT t.variable, min(t.valor) AS minimo, max(t.valor) AS maximo, avg(t.valor) AS promedio,
                  (SELECT count(*) FROM win w WHERE w.variable = t.variable) AS n, u.ultimo, u.t_ultimo
           FROM todo t JOIN ult u USING (variable) GROUP BY t.variable, u.ultimo, u.t_ultimo""",
        {"vars": variables, "s": segundos, "tr": t_ref or _ahora()})
    return {f["variable"]: f for f in filas}


def _parada_tras_saturacion(t_ref: datetime) -> dict | None:
    """Si la bomba se detuvo en los ultimos 10 min y en los 60 s previos a la parada el variador estuvo
    siempre >= 99 %, devuelve los datos del evento (posible disparo de una proteccion del motor)."""
    f = _consulta(
        """WITH on_ AS (SELECT max(time) AS t FROM mediciones WHERE fuente = 'uns'
                       AND variable = 'estado/sistema_funcionando' AND valor >= 0.5
                       AND time <= %(tr)s AND time > %(tr)s - interval '10 minutes'),
                stop AS (SELECT min(m.time) AS t FROM mediciones m, on_ WHERE m.fuente = 'uns'
                       AND m.variable = 'estado/sistema_funcionando' AND m.valor < 0.5
                       AND m.time > on_.t AND m.time <= %(tr)s)
           SELECT stop.t AS t_parada,
                  (SELECT valor FROM mediciones WHERE fuente = 'uns' AND variable = 'actuadores/variador_pct'
                     AND time <= stop.t - interval '60 seconds' ORDER BY time DESC LIMIT 1) AS var_inicio,
                  (SELECT min(valor) FROM mediciones WHERE fuente = 'uns' AND variable = 'actuadores/variador_pct'
                     AND time > stop.t - interval '60 seconds' AND time < stop.t - interval '2 seconds') AS var_min,
                  (SELECT max(time) FROM mediciones WHERE fuente = 'uns' AND variable = 'actuadores/variador_pct'
                     AND valor < 99 AND time < stop.t - interval '2 seconds'
                     AND time > stop.t - interval '10 minutes') AS ultimo_bajo_99
           FROM stop""", {"tr": t_ref})
    if not f or f[0]["t_parada"] is None:
        return None
    r = f[0]
    if r["var_inicio"] is None or r["var_inicio"] < 99 or (r["var_min"] is not None and r["var_min"] < 99):
        return None
    seg = (r["t_parada"] - r["ultimo_bajo_99"]).total_seconds() if r["ultimo_bajo_99"] else None
    return {"hora_parada": _iso(r["t_parada"]), "segundos_al_100_antes_de_parar": _num(seg, 0)}


@mcp.tool(annotations=SOLO_LECTURA)
def consultar_grafo(entidad: str | None = None) -> dict:
    """Knowledge graph del modulo: equipos, sensores, actuadores y mandos con sus variables UNS y relaciones
    causales (alimenta, acciona, impulsa, mide, controla, habilita...). Sin 'entidad' devuelve el grafo completo;
    con 'entidad' (p. ej. 'bomba', 'pid') devuelve sus relaciones de entrada/salida y la cadena aguas arriba."""
    g = _grafo()
    if not entidad:
        return {"modelo": g["modelo"], "nodos": g["nodos"], "relaciones": g["relaciones"],
                "capacidad_observada": g.get("capacidad_observada")}
    e = entidad.strip().lower()
    if e not in g["nodos"]:
        raise ToolError(f"Entidad '{entidad}' no existe. Opciones: {', '.join(g['nodos'])}")
    entra = [r for r in g["relaciones"] if r["a"] == e]
    sale = [r for r in g["relaciones"] if r["de"] == e]
    # aguas arriba: todo lo que influye sobre la entidad (recorrido inverso del grafo)
    vistos, cola, arriba = {e}, [e], []
    while cola:
        x = cola.pop(0)
        for r in g["relaciones"]:
            if r["a"] == x and r["de"] not in vistos and r["rel"] != "mide":   # medir no influye en el proceso
                vistos.add(r["de"]); cola.append(r["de"]); arriba.append(f"{r['de']} --{r['rel']}--> {x}")
    return {"entidad": e, **g["nodos"][e], "relaciones_entrada": entra, "relaciones_salida": sale,
            "aguas_arriba": arriba}


@mcp.tool(annotations=SOLO_LECTURA)
def diagnosticar_lazo(momento: str | None = None) -> dict:
    """Diagnostico del lazo de caudal razonando sobre el knowledge graph y los ultimos 30 s de datos.
    Devuelve UN diagnostico principal (SIN_DATOS, CONTROL_MANUAL_LOCAL, PID_SIN_HABILITAR, BOMBA_DETENIDA,
    TRANSITORIO, SATURADO_FUERA_DE_CAPACIDAD, SATURADO_EN_MINIMO, DESVIACION_SIN_SATURAR o REGULANDO),
    hallazgos secundarios (integrador cargado, nivel bajo, sensores incoherentes), la evidencia numerica,
    la cadena causal del grafo que lo explica y una recomendacion. Usala primero cuando pregunten si el
    caudal sigue al setpoint o por que no. Con 'momento' (ISO 8601, hora de Lima) reproduce el diagnostico en
    un instante pasado, p. ej. para explicar por que se detuvo la bomba a cierta hora."""
    g = _grafo()
    t_ref = None
    if momento:
        try:
            t_ref = datetime.fromisoformat(momento.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"momento no valido: '{momento}'. Usa ISO 8601, p. ej. 2026-10-19T15:17:00") from None
        if t_ref.tzinfo is None:
            t_ref = t_ref.replace(tzinfo=TZ_LIMA)
        if t_ref > _ahora():
            raise ToolError("momento no puede estar en el futuro")
        enlace = {"datos_en_vivo": True, "motivos": []}   # reproduccion historica: no se evalua el enlace actual
    else:
        enlace = _estado_enlace()
    vars_ = ["caudal/pv_pid", "caudal/caudalimetro", "caudal/setpoint_pid", "actuadores/variador_pct",
             "actuadores/valvula_pct", "pid/salida", "pid/mx", "estado/sistema_funcionando",
             "estado/selector_remoto", "estado/selector_local", "estado/nivel_bajo"]
    w = _ventana(vars_, VENTANA_DIAG_S, t_ref)

    def ult(k, d=None):
        return float(w[k]["ultimo"]) if k in w and w[k]["ultimo"] is not None else d

    def rng(k):
        return float(w[k]["maximo"]) - float(w[k]["minimo"]) if k in w else None

    sp, pv, cq = ult("caudal/setpoint_pid"), ult("caudal/pv_pid"), ult("caudal/caudalimetro")
    pv_prom = float(w["caudal/pv_pid"]["promedio"]) if "caudal/pv_pid" in w else None
    var, sal, mx, valv = ult("actuadores/variador_pct"), ult("pid/salida"), ult("pid/mx"), ult("actuadores/valvula_pct")
    bomba, remoto, local, nbajo = (ult("estado/sistema_funcionando"), ult("estado/selector_remoto"),
                                   ult("estado/selector_local"), ult("estado/nivel_bajo"))
    error = None if sp is None or pv_prom is None else pv_prom - sp
    evid = {"setpoint_lpm": _num(sp, 2), "caudal_pv_lpm": _num(pv, 2), "caudal_promedio_30s_lpm": _num(pv_prom, 2),
            "error_lpm": _num(error, 2), "variacion_caudal_30s_lpm": _num(rng("caudal/pv_pid"), 2),
            "caudalimetro_lpm": _num(cq, 2), "variador_pct": _num(var, 1), "salida_pid_pct": _num(sal, 1),
            "suma_integral_mx": _num(mx, 3), "valvula_pct": _num(valv, 1), "bomba_en_marcha": bomba,
            "remoto": remoto, "local": local, "nivel_bajo": nbajo}
    secundarios = []
    resp = {"consultado": _iso(_ahora()), "momento_evaluado": _iso(t_ref or _ahora()),
            "modo": "reproduccion historica" if t_ref else "en vivo", "ventana_s": VENTANA_DIAG_S, "evidencia": evid}

    def fin(diag, explicacion, cadena, recomendacion):
        resp.update({"diagnostico": diag, "explicacion": explicacion, "cadena_causal": _cadena(g, cadena),
                     "aristas_causales": _aristas(g, cadena),
                     "hallazgos_secundarios": secundarios, "recomendacion": recomendacion})
        return resp

    # hallazgos secundarios (no excluyentes)
    if nbajo and nbajo >= 0.5:
        secundarios.append({"hallazgo": "NIVEL_BAJO", "detalle": "Alarma de nivel bajo en el tanque: riesgo de que "
                            "la bomba aspire aire", "cadena": _cadena(g, [("sensor_nivel", "bomba"), ("tanque", "bomba")]), "aristas": _aristas(g, [("sensor_nivel", "bomba"), ("tanque", "bomba")])})
    if bomba is not None and bomba < 0.5 and sal is not None and sal >= 95 and (sp or 0) > 1:
        secundarios.append({"hallazgo": "INTEGRADOR_CARGADO", "detalle": f"Con la bomba parada el PID sigue integrando "
                            f"error y su salida esta en {sal:.0f} % (Mx={mx}). Al arrancar habra un sobreimpulso grande.",
                            "cadena": _cadena(g, [("pid", "variador"), ("variador", "bomba")]), "aristas": _aristas(g, [("pid", "variador"), ("variador", "bomba")])})
    if (bomba or 0) >= 0.5 and pv is not None and cq is not None and (rng("caudal/pv_pid") or 0) <= TOL_SENSOR_LPM \
            and abs(pv - cq) > TOL_SENSOR_LPM:
        secundarios.append({"hallazgo": "SENSORES_INCOHERENTES", "detalle": f"PV del PID {pv:.1f} vs caudalimetro "
                            f"{cq:.1f} L/min en regimen estable", "cadena": _cadena(g, [("caudalimetro", "linea"), ("pid", "caudalimetro")]), "aristas": _aristas(g, [("caudalimetro", "linea"), ("pid", "caudalimetro")])})

    # diagnostico principal (en orden de precedencia)
    if not enlace["datos_en_vivo"]:
        return fin("SIN_DATOS", "No hay datos en vivo: " + "; ".join(enlace["motivos"]), [],
                   "Revisar el conector edge (ventana CONECTOR EDGE) y la conexion con el PLC.")
    if local and local >= 0.5:
        return fin("CONTROL_MANUAL_LOCAL", "El selector esta en LOCAL: el potenciometro gobierna el variador y el PID "
                   "no tiene efecto. No se evalua el seguimiento del setpoint.",
                   [("potenciometro", "variador"), ("selector", "pid")], "Pasar el selector a REMOTO para que regule el PID.")
    if not remoto or remoto < 0.5:
        return fin("PID_SIN_HABILITAR", "El selector no esta en REMOTO: el PID no esta habilitado.",
                   [("selector", "pid")], "Poner el selector en REMOTO.")
    if bomba is None or bomba < 0.5:
        ev = _parada_tras_saturacion(t_ref or _ahora())
        if ev:
            secundarios.append({"hallazgo": "PARADA_TRAS_SATURACION", "detalle":
                f"La bomba se detuvo a las {ev['hora_parada'][11:19]} despues de "
                f"{ev['segundos_al_100_antes_de_parar'] or 'al menos 60'} s con el variador al 100 %. Patron compatible con el "
                "disparo de la proteccion del motor (guardamotor/termico) por trabajar a plena carga. No repetir la "
                "condicion sin revisar el equipo con el responsable del laboratorio.",
                "cadena": _cadena(g, [("variador", "bomba"), ("proteccion_motor", "bomba")]), "aristas": _aristas(g, [("variador", "bomba"), ("proteccion_motor", "bomba")])})
        return fin("BOMBA_DETENIDA", f"La bomba esta detenida: el caudal es {pv or 0:.1f} L/min aunque el setpoint es "
                   f"{sp or 0:.1f} L/min. El error no es un problema del control.",
                   [("variador", "bomba"), ("bomba", "linea")], "Arrancar la bomba (START remoto) si se requiere caudal.")
    if (rng("caudal/pv_pid") or 0) > TOL_SENSOR_LPM or (rng("caudal/setpoint_pid") or 0) > 0.5:
        return fin("TRANSITORIO", "El caudal o el setpoint cambiaron en los ultimos 30 s: el lazo se esta "
                   "acomodando; el diagnostico de regimen no es concluyente todavia.",
                   [("pid", "variador"), ("variador", "bomba"), ("bomba", "linea")], "Volver a consultar en 30-60 s.")
    if error is not None and error < -TOL_ERROR_LPM and var is not None and var >= 99:
        cap = g.get("capacidad_observada", {})
        return fin("SATURADO_FUERA_DE_CAPACIDAD",
                   f"El PID pide el maximo (salida {sal or 0:.0f} %, Mx={mx}) y el variador esta al {var:.0f} % con la valvula "
                   f"al {valv or 0:.0f} %, pero el caudal se queda en {pv_prom:.1f} L/min, {abs(error):.1f} L/min por debajo del "
                   f"setpoint ({sp:.1f}). El equipo no puede entregar ese caudal: no es una falla de control ni de sensores.",
                   [("pid", "variador"), ("variador", "bomba"), ("bomba", "linea"), ("valvula", "linea")],
                   f"Bajar el setpoint por debajo de {cap.get('caudal_max_lpm', round(pv_prom, 1))} L/min (capacidad observada). "
                   f"{cap.get('riesgo', '')} Si la capacidad bajo respecto a pruebas anteriores, revisar bomba y valvula.".strip())
    if error is not None and error > TOL_ERROR_LPM and var is not None and var <= 1:
        return fin("SATURADO_EN_MINIMO", f"El variador esta al minimo y aun asi el caudal ({pv_prom:.1f}) supera el "
                   f"setpoint ({sp:.1f}).", [("variador", "bomba"), ("bomba", "linea")],
                   "Subir el setpoint por encima del caudal minimo del equipo.")
    if error is not None and abs(error) > TOL_ERROR_LPM:
        return fin("DESVIACION_SIN_SATURAR", f"Error sostenido de {error:+.1f} L/min con el variador al {var or 0:.0f} % "
                   "(sin saturar): el PID tiene margen pero no corrige.",
                   [("pid", "variador"), ("pid", "caudalimetro")],
                   "Revisar la sintonia (Ti) o una perturbacion; verificar la coherencia de sensores.")
    return fin("REGULANDO", f"El caudal sigue al setpoint: promedio {pv_prom:.2f} L/min contra {sp:.2f} "
               f"(error {error:+.2f} L/min) con el variador al {var or 0:.0f} %, con margen.",
               [("pid", "variador"), ("variador", "bomba"), ("bomba", "linea"), ("caudalimetro", "linea")],
               "Sin accion. El lazo opera normalmente.")


# ----------------------------------------------------------------------------- arranque
def _probar() -> None:
    """Ejecuta cada herramienta una vez contra la base real y muestra el resultado."""
    pruebas = [
        ("listar_variables", lambda: listar_variables()),
        ("obtener_estado_plc", lambda: obtener_estado_plc()),
        ("obtener_lectura", lambda: obtener_lectura(["caudal/pv_pid", "caudal/setpoint_pid"])),
        ("consultar_historial", lambda: consultar_historial("caudal/pv_pid", minutos=30, puntos_max=10)),
        ("comparar_con_rango", lambda: comparar_con_rango()),
        ("verificar_coherencia_caudal", lambda: verificar_coherencia_caudal()),
        ("comparar_con_historico_lvm", lambda: comparar_con_historico_lvm()),
        ("consultar_grafo", lambda: consultar_grafo("bomba")),
        ("diagnosticar_lazo", lambda: diagnosticar_lazo()),
    ]
    for nombre, f in pruebas:
        print(f"\n===== {nombre} =====")
        try:
            print(json.dumps(f(), ensure_ascii=False, indent=2, default=str)[:2500])
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor MCP solo lectura del modulo de caudal MCC-09")
    ap.add_argument("--probar", action="store_true", help="ejecuta todas las herramientas una vez y termina")
    if ap.parse_args().probar:
        _probar()
    else:
        mcp.run()
