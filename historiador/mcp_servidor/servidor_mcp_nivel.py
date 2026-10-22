"""
Servidor MCP SOLO LECTURA del modulo de control de nivel MCN-09/001 (laboratorio USS).  v1.0

PLC Allen-Bradley MicroLogix 1100 + 1762-IF2OF2. Datos del UNS guardados en TimescaleDB por el
servicio 'ingestor-nivel' con prefijo 'nivel-mcn09/' (p. ej. 'nivel-mcn09/nivel/cm').
- Se conecta con el rol mcp_lector (solo SELECT) y abre cada sesion en modo read-only.
- No tiene ninguna ruta hacia el PLC.
- Las herramientas aceptan los nombres con o sin prefijo ('nivel/cm' o 'nivel-mcn09/nivel/cm')
  y devuelven los nombres sin prefijo.

Prueba manual:
    set MCP_DSN=postgresql://mcp_lector:TU_CLAVE@localhost:5432/uns
    python mcp_servidor/servidor_mcp_nivel.py --probar
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
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

def _dsn_por_defecto() -> str:
    """Si no hay MCP_DSN, arma la conexion con MCP_READER_PASSWORD del .env del historiador
    (asi la configuracion de Claude Desktop no necesita copiar la clave)."""
    clave = os.getenv("MCP_READER_PASSWORD")
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not clave and os.path.exists(env):
        with open(env, encoding="utf-8", errors="replace") as f:
            for linea in f:
                if linea.strip().startswith("MCP_READER_PASSWORD="):
                    clave = linea.split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://mcp_lector:{clave or 'lector_cambiar'}@localhost:5432/uns"


DSN = os.getenv("MCP_DSN") or _dsn_por_defecto()
BASE = os.getenv("UNS_BASE_NIVEL", "uss/campus/lab-automatizacion/sl01la07/nivel-mcn09")
PREFIJO = "nivel-mcn09/"
HEARTBEAT_MAX_S = float(os.getenv("HEARTBEAT_MAX_S", "30"))
VALOR_MAX_S = float(os.getenv("VALOR_MAX_S", "90"))
TZ_LIMA = timezone(timedelta(hours=-5))
VARIABLE_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)+$")
MAX_MINUTOS = 60 * 24 * 31
SOLO_LECTURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# Datos del proceso (manual Inducontrol MCN-09/001 + calibracion 20-oct-2026)
RANGO_OPERATIVO_CM = (0.0, 35.0)       # rango de trabajo segun el manual
LIMITE_SENSOR_CM = 40.0                # por encima el sensor ultrasonico satura (medido)
LITROS_POR_CM_T2 = 43.0 / 60.0         # T2 acrilico 43 L, 60 cm de alto (supone seccion constante)
UMBRAL_TENDENCIA_CM_S = 0.03           # |pendiente| menor a esto = nivel estable
RANGO_FISICO_CM = (-2.0, 42.0)         # fuera de esto el valor es imposible: saturacion o caida del sensor
VENTANA_S = 30

INSTRUCCIONES = """Servidor de SOLO LECTURA del modulo de control de nivel MCN-09/001 (PLC Allen-Bradley MicroLogix 1100,
laboratorio de automatizacion USS). Datos del Unified Namespace guardados en TimescaleDB.
Reglas para el agente:
- Nunca inventes valores, unidades ni limites: usa solo lo que devuelven las herramientas.
- Menciona siempre unidad, hora o periodo y si el dato esta VIGENTE o DESACTUALIZADO.
- Comunica las advertencias (rango del fabricante sin validar, variable en hipotesis, sensor saturado...).
- No puedes modificar el proceso: si piden arrancar, parar o cambiar el setpoint, explica que es solo lectura.
Contexto del proceso: la bomba lleva agua del tanque T1 (reserva, 78 L) al tanque T2 (acrilico, 43 L, 60 cm),
donde un sensor ultrasonico mide el nivel ('nivel/cm', calibrado; rango de trabajo 0-35 cm, el sensor satura
cerca de 40 cm). En modo LOCAL la velocidad la fija el potenciometro del tablero; en REMOTO el PID del PLC
necesita el HMI o el SCADA, que hoy no estan operativos. Si T1 queda en nivel bajo la bomba se detiene sola.
Para preguntas de que esta pasando o por que, usa primero diagnosticar_nivel; consultar_grafo describe los
equipos y sus relaciones causales."""

mcp = MCPServer("nivel-mcn09", instructions=INSTRUCCIONES, version="1.0")


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


def _corto(variable: str) -> str:
    return variable[len(PREFIJO):] if variable.startswith(PREFIJO) else variable


def _validar_variable(variable: str) -> str:
    """Devuelve el nombre COMPLETO (con prefijo) tal como esta en la base."""
    v = (variable or "").strip().strip("/")
    if v.startswith(BASE):
        v = v[len(BASE):].strip("/").removeprefix("funcional/")
    v = v.removeprefix(PREFIJO)
    if not VARIABLE_RE.match(v):
        raise ToolError(f"Nombre de variable no valido: '{variable}'. Usa listar_variables para ver los nombres.")
    completo = PREFIJO + v
    existe = _consulta("SELECT 1 FROM variables WHERE variable = %s UNION ALL "
                       "SELECT 1 FROM mediciones WHERE variable = %s LIMIT 1", (completo, completo))
    if not existe:
        raise ToolError(f"La variable '{v}' no existe en el historiador del modulo de nivel. Usa listar_variables.")
    return completo


def _periodo(minutos: float | None, inicio: str | None, fin: str | None) -> tuple[datetime, datetime]:
    def parse(s: str) -> datetime:
        try:
            t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"Fecha no valida: '{s}'. Usa ISO 8601, p. ej. 2026-10-20T13:30") from None
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
    if (t1 - t0) > timedelta(days=366 * 20):
        raise ToolError("Periodo demasiado largo")
    return t0, t1


def _estado_enlace() -> dict:
    filas = _consulta(
        """SELECT DISTINCT ON (topic) topic, texto, time FROM eventos
           WHERE topic IN (%(e)s, %(p)s, %(h)s) ORDER BY topic, time DESC""",
        {"e": f"{BASE}/funcional/edge/estado", "p": f"{BASE}/funcional/plc/conexion",
         "h": f"{BASE}/funcional/edge/heartbeat"})
    d = {f["topic"].rsplit("/", 2)[-2] + "/" + f["topic"].rsplit("/", 1)[-1]: f for f in filas}
    edge, plc, hb = d.get("edge/estado"), d.get("plc/conexion"), d.get("edge/heartbeat")
    edad_hb = (_ahora() - hb["time"]).total_seconds() if hb else None
    motivos = []
    if not edge or edge["texto"] != "ONLINE":
        motivos.append(f"conector edge {edge['texto'] if edge else 'sin reportar'}")
    if not plc or plc["texto"] != "CONECTADO":
        motivos.append(f"PLC {plc['texto'] if plc else 'sin reportar'}")
    if edad_hb is None or edad_hb > HEARTBEAT_MAX_S:
        motivos.append("sin latido reciente del conector" + (f" (hace {edad_hb:.0f} s)" if edad_hb else ""))
    return {"datos_en_vivo": not motivos, "conector_edge": edge["texto"] if edge else None,
            "conexion_plc": plc["texto"] if plc else None, "ultimo_latido": _iso(hb["time"]) if hb else None,
            "segundos_desde_latido": _num(edad_hb, 1), "motivos": motivos}


def _ultimos(cortos: list[str], t_ref: datetime | None = None) -> dict[str, dict]:
    completos = [PREFIJO + c for c in cortos]
    filas = _consulta(
        """SELECT DISTINCT ON (m.variable) m.variable, m.valor, m.unidad, m.time, m.direccion, v.descripcion
           FROM mediciones m LEFT JOIN variables v USING (variable)
           WHERE m.fuente = 'uns' AND m.variable = ANY(%s) AND m.time <= %s
           ORDER BY m.variable, m.time DESC""", (completos, t_ref or _ahora()))
    return {_corto(f["variable"]): f for f in filas}


def _b(u: dict, k: str) -> bool | None:
    return None if k not in u else bool(u[k]["valor"] >= 0.5)


def _v(u: dict, k: str) -> float | None:
    return None if k not in u else float(u[k]["valor"])


def _modo(u: dict) -> str:
    remoto, local = _b(u, "estado/selector_remoto"), _b(u, "estado/selector_local")
    if remoto is None and local is None:
        return "DESCONOCIDO"
    return "REMOTO" if remoto else "LOCAL" if local else "SELECTOR_EN_0"


def _tendencia(t_ref: datetime | None = None, segundos: float = VENTANA_S) -> dict:
    """Pendiente del nivel (cm/s) por regresion lineal en la ventana, y caudal neto estimado hacia T2."""
    tr = t_ref or _ahora()
    f = _consulta(
        """SELECT count(*) AS n, regr_slope(valor, extract(epoch FROM time)) AS pendiente,
                  min(valor) AS minimo, max(valor) AS maximo
           FROM mediciones WHERE fuente = 'uns' AND variable = %s
             AND time > %s - make_interval(secs => %s) AND time <= %s""",
        (PREFIJO + "nivel/cm", tr, segundos, tr))[0]
    p = None if f["pendiente"] is None else float(f["pendiente"])
    if p is None or f["n"] < 4:
        estado = "SIN_DATOS_SUFICIENTES"
    elif p > UMBRAL_TENDENCIA_CM_S:
        estado = "SUBIENDO"
    elif p < -UMBRAL_TENDENCIA_CM_S:
        estado = "BAJANDO"
    else:
        estado = "ESTABLE"
    return {"ventana_s": segundos, "muestras": f["n"], "tendencia": estado,
            "pendiente_cm_min": _num(p * 60, 2) if p is not None else None,
            "caudal_neto_estimado_l_min": _num(p * 60 * LITROS_POR_CM_T2, 2) if p is not None else None,
            "nota_caudal": "Estimacion: pendiente del nivel x 0,717 L/cm (T2 de 43 L en 60 cm, seccion constante). "
                           "Es el caudal NETO (entrada de la bomba menos salida por valvulas)."}


# ----------------------------------------------------------------------------- herramientas
@mcp.tool(annotations=SOLO_LECTURA)
def listar_variables() -> dict:
    """Lista las variables del modulo de nivel en el historiador (nombre UNS, direccion en el PLC, unidad,
    descripcion, si esta confirmada o en hipotesis) con su ultimo dato en vivo y cuantos datos historicos tiene."""
    filas = _consulta(
        """WITH u AS (SELECT DISTINCT ON (variable) variable, time FROM mediciones
                      WHERE fuente = 'uns' AND variable LIKE %(p)s ORDER BY variable, time DESC),
                h AS (SELECT variable, count(*) AS n FROM mediciones
                      WHERE fuente = 'lvm' AND variable LIKE %(p)s GROUP BY variable),
                todas AS (SELECT variable FROM variables WHERE variable LIKE %(p)s
                          UNION SELECT variable FROM u UNION SELECT variable FROM h)
           SELECT t.variable, v.tag_plc, v.direccion, v.unidad, v.descripcion,
                  u.time AS ultimo_dato_vivo, coalesce(h.n, 0) AS muestras_historicas
           FROM todas t LEFT JOIN variables v USING (variable) LEFT JOIN u USING (variable) LEFT JOIN h USING (variable)
           ORDER BY t.variable""", {"p": PREFIJO + "%"})
    return {"base_uns": f"{BASE}/funcional/",
            "variables": [{**f, "variable": _corto(f["variable"]), "ultimo_dato_vivo": _iso(f["ultimo_dato_vivo"])}
                          for f in filas],
            "nota": "Usa los nombres tal cual (p. ej. 'nivel/cm'). Las descripciones indican si la variable esta "
                    "confirmada o es una hipotesis."}


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_lectura(variables: list[str]) -> dict:
    """Ultimo valor en vivo de una o varias variables (maximo 20) con unidad, hora, antiguedad y si esta
    VIGENTE o DESACTUALIZADO. Ejemplo: ["nivel/cm", "estado/bomba_marcha"]."""
    if isinstance(variables, str):
        variables = [variables]
    if not variables or len(variables) > 20:
        raise ToolError("Indica entre 1 y 20 variables")
    completos = [_validar_variable(v) for v in variables]
    enlace = _estado_enlace()
    ult = _ultimos([_corto(c) for c in completos])
    ahora = _ahora()
    salida = []
    for c in completos:
        n = _corto(c)
        f = ult.get(n)
        if not f:
            salida.append({"variable": n, "estado": "SIN_DATOS", "motivo": "nunca se recibio un dato en vivo"})
            continue
        edad = (ahora - f["time"]).total_seconds()
        estado, motivo = "VIGENTE", None
        if not enlace["datos_en_vivo"]:
            estado, motivo = "DESACTUALIZADO", "; ".join(enlace["motivos"])
        elif edad > VALOR_MAX_S:
            estado, motivo = "DESACTUALIZADO", f"sin actualizacion hace {edad:.0f} s"
        salida.append({"variable": n, "valor": _num(f["valor"], 3), "unidad": f["unidad"], "hora": _iso(f["time"]),
                       "antiguedad_s": _num(edad, 1), "estado": estado, "motivo": motivo,
                       "direccion_plc": f["direccion"], "descripcion": f["descripcion"]})
    return {"consultado": _iso(ahora), "enlace": enlace, "lecturas": salida}


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_estado_plc() -> dict:
    """Estado general del modulo de nivel: conexion del conector y del PLC, modo (LOCAL/REMOTO/selector en 0),
    bomba, nivel actual en cm y su tendencia, potenciometro, valvula, agua en T1 y alarmas."""
    enlace = _estado_enlace()
    u = _ultimos(["estado/selector_remoto", "estado/selector_local", "estado/bomba_marcha",
                  "estado/tanque1_con_agua", "estado/alarma_nivel_bajo_tanque1", "estado/mando_i03",
                  "estado/piloto_o00", "nivel/cm", "nivel/fuera_rango_sensor", "bomba/potenciometro_raw",
                  "bomba/frecuencia_estimada_hz", "valvula/abriendo", "valvula/cerrando"])
    nivel = _v(u, "nivel/cm")
    advertencias = list(enlace["motivos"])
    if _b(u, "estado/tanque1_con_agua") is False:
        advertencias.append("Tanque T1 (reserva) en NIVEL BAJO: la bomba no puede funcionar")
    if _b(u, "nivel/fuera_rango_sensor"):
        advertencias.append(f"Nivel por encima del rango util del sensor (~{LIMITE_SENSOR_CM:.0f} cm): valor no fiable")
    elif nivel is not None and nivel > RANGO_OPERATIVO_CM[1]:
        advertencias.append(f"Nivel {nivel:.1f} cm sobre el rango de trabajo del fabricante (0-35 cm)")
    return {
        "consultado": _iso(_ahora()), "enlace": enlace, "modo": _modo(u),
        "bomba_en_marcha": _b(u, "estado/bomba_marcha"),
        "nivel_t2_cm": _num(nivel, 1), "hora_nivel": _iso(u["nivel/cm"]["time"]) if "nivel/cm" in u else None,
        "tendencia_nivel": _tendencia(),
        "potenciometro_raw": _v(u, "bomba/potenciometro_raw"),
        "frecuencia_estimada_hz": _v(u, "bomba/frecuencia_estimada_hz"),
        "valvula_abriendo": _b(u, "valvula/abriendo"), "valvula_cerrando": _b(u, "valvula/cerrando"),
        "tanque1_con_agua": _b(u, "estado/tanque1_con_agua"),
        "alarma_nivel_bajo_t1": _b(u, "estado/alarma_nivel_bajo_tanque1"),
        "hipotesis_i03_o00": {"I:0/3": _b(u, "estado/mando_i03"), "O:0/0": _b(u, "estado/piloto_o00"),
                              "nota": "Probable interruptor y piloto de NIVEL ALTO de T1 (sin confirmar)"},
        "advertencias": advertencias,
    }


@mcp.tool(annotations=SOLO_LECTURA)
def consultar_historial(variable: str = "nivel/cm", minutos: float | None = 60, inicio: str | None = None,
                        fin: str | None = None, fuente: str = "uns", puntos_max: int = 60) -> dict:
    """Historial de una variable: estadisticas (promedio, minimo, maximo, desviacion, inicial, final, variacion)
    y una serie resumida de hasta 'puntos_max' puntos. Periodo: ultimos 'minutos' o 'inicio'/'fin' ISO 8601
    (hora de Lima si no tiene zona). fuente='uns' en vivo o 'lvm' historicos del SCADA original."""
    completo = _validar_variable(variable)
    if fuente not in ("uns", "lvm"):
        raise ToolError("fuente debe ser 'uns' o 'lvm'")
    t0, t1 = _periodo(minutos, inicio, fin)
    puntos_max = max(5, min(int(puntos_max), 500))
    st = _consulta(
        """SELECT count(*) AS n, avg(valor) AS promedio, min(valor) AS minimo, max(valor) AS maximo,
                  stddev_samp(valor) AS desviacion, min(time) AS primero, max(time) AS ultimo,
                  (array_agg(valor ORDER BY time))[1] AS valor_inicial,
                  (array_agg(valor ORDER BY time DESC))[1] AS valor_final, max(unidad) AS unidad
           FROM mediciones WHERE variable = %s AND fuente = %s AND time >= %s AND time < %s""",
        (completo, fuente, t0, t1))[0]
    resp = {"variable": _corto(completo), "fuente": fuente, "periodo": {"inicio": _iso(t0), "fin": _iso(t1)},
            "unidad": st["unidad"], "muestras": st["n"], "advertencias": []}
    if not st["n"]:
        resp["advertencias"].append("No hay datos en ese periodo")
        ult = _consulta("SELECT max(time) AS t FROM mediciones WHERE variable = %s AND fuente = %s",
                        (completo, fuente))[0]["t"]
        resp["ultimo_dato_disponible"] = _iso(ult)
        return resp
    paso = max(1, math.ceil((t1 - t0).total_seconds() / puntos_max))
    serie = _consulta(
        """SELECT date_bin(make_interval(secs => %s), time, %s) AS t, avg(valor) AS v, min(valor) AS mn, max(valor) AS mx
           FROM mediciones WHERE variable = %s AND fuente = %s AND time >= %s AND time < %s
           GROUP BY 1 ORDER BY 1""", (paso, t0, completo, fuente, t0, t1))
    resp.update({
        "estadisticas": {"promedio": _num(st["promedio"]), "minimo": _num(st["minimo"]), "maximo": _num(st["maximo"]),
                         "desviacion": _num(st["desviacion"]), "valor_inicial": _num(st["valor_inicial"]),
                         "valor_final": _num(st["valor_final"]),
                         "variacion": _num(st["valor_final"] - st["valor_inicial"]),
                         "primer_dato": _iso(st["primero"]), "ultimo_dato": _iso(st["ultimo"])},
        "intervalo_serie_s": paso,
        "serie": [{"t": _iso(f["t"]), "promedio": _num(f["v"]), "min": _num(f["mn"]), "max": _num(f["mx"])}
                  for f in serie]})
    if fuente == "uns":
        resp["advertencias"].append("El conector publica por cambio o cada 60 s: muestras no equiespaciadas.")
    if completo == PREFIJO + "nivel/cm":
        inval = _consulta(
            """SELECT count(*) AS n FROM mediciones WHERE variable = %s AND fuente = %s AND time >= %s AND time < %s
                 AND (valor < %s OR valor > %s)""", (completo, fuente, t0, t1, *RANGO_FISICO_CM))[0]["n"]
        if inval:
            resp["muestras_fisicamente_invalidas"] = inval
            resp["advertencias"].append(
                f"{inval} muestras fuera de {RANGO_FISICO_CM[0]:g}..{RANGO_FISICO_CM[1]:g} cm (saturacion del sensor por "
                "encima de ~40 cm o caida de senal): las estadisticas las incluyen; no las interpretes como nivel real.")
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def comparar_con_rango(variable: str = "nivel/cm", minutos: float = 5) -> dict:
    """Compara el valor actual y los ultimos 'minutos' de una variable con su rango registrado (para 'nivel/cm':
    0-35 cm, rango de trabajo del fabricante). Indica si esta dentro, % de muestras fuera y quien valido el rango."""
    completo = _validar_variable(variable)
    t0, t1 = _periodo(minutos, None, None)
    rango = _consulta("SELECT minimo, maximo, unidad, validado_por, nota FROM rangos_validados WHERE variable = %s",
                      (completo,))
    actual = obtener_lectura([completo])["lecturas"][0]
    resp = {"variable": _corto(completo), "periodo": {"inicio": _iso(t0), "fin": _iso(t1)},
            "lectura_actual": actual, "advertencias": []}
    if not rango:
        resp["advertencias"].append("Esta variable no tiene rango registrado; no se puede evaluar.")
        return resp
    r = rango[0]
    resp["rango"] = dict(r)
    quien = (r["validado_por"] or "").upper()
    if quien == "PENDIENTE":
        resp["advertencias"].append("RANGO PROVISIONAL: aun no lo valida el responsable del laboratorio.")
    elif quien.startswith("FABRICANTE"):
        resp["advertencias"].append("Rango tomado del manual del fabricante; falta la validacion del responsable "
                                    "del laboratorio.")
    st = _consulta(
        """SELECT count(*) AS n, count(*) FILTER (WHERE valor < %s OR valor > %s) AS fuera,
                  avg(valor) AS promedio, min(valor) AS minimo, max(valor) AS maximo
           FROM mediciones WHERE variable = %s AND fuente = 'uns' AND time >= %s AND time < %s""",
        (r["minimo"], r["maximo"], completo, t0, t1))[0]
    resp["periodo_stats"] = {"muestras": st["n"], "fuera_de_rango": st["fuera"],
                             "porcentaje_fuera": _num(100 * st["fuera"] / st["n"], 1) if st["n"] else None,
                             "promedio": _num(st["promedio"]), "minimo": _num(st["minimo"]),
                             "maximo": _num(st["maximo"])}
    v = actual.get("valor")
    resp["evaluacion"] = "SIN_DATO_ACTUAL" if v is None else ("DENTRO" if r["minimo"] <= v <= r["maximo"] else "FUERA")
    if actual.get("estado") != "VIGENTE":
        resp["advertencias"].append(f"La lectura actual esta {actual.get('estado')}: {actual.get('motivo')}")
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def diagnosticar_nivel(momento: str | None = None) -> dict:
    """Diagnostico del modulo de nivel con reglas sobre el estado y los ultimos 30 s. Devuelve UN diagnostico
    principal (SIN_DATOS, SELECTOR_EN_0, REMOTO_SIN_SUPERVISOR, TANQUE1_NIVEL_BAJO, APERTURA_INICIAL_VALVULA,
    BOMBA_DETENIDA, LLENANDO, NIVEL_ESTABLE o VACIANDO_CON_BOMBA), hallazgos secundarios, evidencia numerica
    (nivel, tendencia en cm/min, caudal neto estimado) y una recomendacion. Usala primero para preguntas de
    que esta pasando o por que. Con 'momento' (ISO 8601, hora de Lima) reproduce el diagnostico en el pasado."""
    t_ref = None
    if momento:
        try:
            t_ref = datetime.fromisoformat(momento.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"momento no valido: '{momento}'. Usa ISO 8601, p. ej. 2026-10-20T13:39:45") from None
        if t_ref.tzinfo is None:
            t_ref = t_ref.replace(tzinfo=TZ_LIMA)
        if t_ref > _ahora():
            raise ToolError("momento no puede estar en el futuro")
        enlace = {"datos_en_vivo": True, "motivos": []}
    else:
        enlace = _estado_enlace()
    u = _ultimos(["estado/selector_remoto", "estado/selector_local", "estado/bomba_marcha",
                  "estado/tanque1_con_agua", "nivel/cm", "nivel/fuera_rango_sensor", "valvula/abriendo",
                  "bomba/potenciometro_raw", "bomba/frecuencia_estimada_hz"], t_ref)
    modo, bomba = _modo(u), _b(u, "estado/bomba_marcha")
    nivel, t1_ok = _v(u, "nivel/cm"), _b(u, "estado/tanque1_con_agua")
    tend = _tendencia(t_ref)
    evid = {"modo": modo, "bomba_en_marcha": bomba, "nivel_t2_cm": _num(nivel, 1), **tend,
            "tanque1_con_agua": t1_ok, "valvula_abriendo": _b(u, "valvula/abriendo"),
            "potenciometro_raw": _v(u, "bomba/potenciometro_raw"),
            "frecuencia_estimada_hz": _v(u, "bomba/frecuencia_estimada_hz")}
    resp = {"consultado": _iso(_ahora()), "momento_evaluado": _iso(t_ref or _ahora()),
            "modo_consulta": "reproduccion historica" if t_ref else "en vivo", "evidencia": evid}
    sec = []
    if _b(u, "nivel/fuera_rango_sensor"):
        sec.append({"hallazgo": "SENSOR_SATURADO", "detalle": f"El agua supera ~{LIMITE_SENSOR_CM:.0f} cm: el sensor "
                    "ultrasonico satura y el nivel reportado no es fiable."})
    elif nivel is not None and nivel > RANGO_OPERATIVO_CM[1]:
        sec.append({"hallazgo": "SOBRE_RANGO_DE_TRABAJO", "detalle": f"Nivel {nivel:.1f} cm por encima de 35 cm "
                    "(rango de trabajo del fabricante)."})
    if bomba and t1_ok is False:
        sec.append({"hallazgo": "T1_BAJO_CON_BOMBA", "detalle": "T1 en nivel bajo con la bomba marcando en marcha: "
                    "la parada deberia ser inmediata."})

    def fin(diag, explicacion, recomendacion):
        pares = list(CADENAS.get(diag, []))
        if diag == "BOMBA_DETENIDA" and tend["tendencia"] == "BAJANDO":
            pares.append(("tanque_t2", "tanque_t1"))
        g = _grafo()
        resp.update({"diagnostico": diag, "explicacion": explicacion, "hallazgos_secundarios": sec,
                     "cadena_causal": _cadena(g, pares), "aristas_causales": _aristas(g, pares),
                     "recomendacion": recomendacion})
        return resp

    cm_min = tend["pendiente_cm_min"]
    if not enlace["datos_en_vivo"]:
        return fin("SIN_DATOS", "No hay datos en vivo: " + "; ".join(enlace["motivos"]),
                   "Revisar el conector edge del MicroLogix y la conexion con el PLC (192.168.114.9).")
    if modo == "SELECTOR_EN_0":
        return fin("SELECTOR_EN_0", "El selector LOCAL/REMOTO esta en la posicion 0: el sistema no opera.",
                   "Poner el selector en LOCAL para operar con el potenciometro.")
    if modo == "REMOTO":
        return fin("REMOTO_SIN_SUPERVISOR", "Selector en REMOTO: el PID del PLC espera setpoint y parametros del HMI "
                   "o del SCADA, que hoy no estan operativos; en este modo el PLC solo abre la valvula.",
                   "Para operar hoy usar LOCAL. Recuperar el HMI queda fuera del alcance de solo lectura.")
    if t1_ok is False:
        return fin("TANQUE1_NIVEL_BAJO", "El tanque T1 (reserva) esta en nivel bajo: el interruptor de nivel detiene "
                   "la bomba para que no trabaje en seco.", "Rellenar T1 por la valvula V1 hasta quedar entre los "
                   "interruptores de nivel bajo y alto.")
    if _b(u, "valvula/abriendo"):
        return fin("APERTURA_INICIAL_VALVULA", "El PLC esta abriendo la valvula proporcional (secuencia de inicio de "
                   "35 s al entrar en modo).", "Esperar a que termine la apertura antes de evaluar el nivel.")
    if not bomba:
        txt = "La bomba esta detenida."
        if cm_min is not None and cm_min < -UMBRAL_TENDENCIA_CM_S * 60:
            txt += f" El nivel de T2 baja a {abs(cm_min):.1f} cm/min: T2 se vacia hacia T1 por las valvulas."
        return fin("BOMBA_DETENIDA", txt, "Pulsar ARRANQUE MANUAL (en LOCAL) si se requiere llenar T2.")
    if tend["tendencia"] == "SUBIENDO":
        falta = None
        if nivel is not None and cm_min and cm_min > 0:
            falta = (RANGO_OPERATIVO_CM[1] - nivel) / cm_min
        return fin("LLENANDO", f"La bomba llena T2: nivel {nivel:.1f} cm subiendo a {cm_min:.1f} cm/min "
                   f"(caudal neto ~{tend['caudal_neto_estimado_l_min']} L/min)."
                   + (f" Llegaria a 35 cm en ~{falta:.1f} min." if falta and falta > 0 else ""),
                   "Vigilar que no supere 35 cm (rango de trabajo) ni ~40 cm (saturacion del sensor).")
    if tend["tendencia"] == "BAJANDO":
        return fin("VACIANDO_CON_BOMBA", f"La bomba esta en marcha pero el nivel baja a {abs(cm_min):.1f} cm/min: "
                   "la salida por las valvulas supera la entrada.",
                   "Subir el potenciometro o cerrar la valvula manual de salida si se quiere mantener el nivel.")
    return fin("NIVEL_ESTABLE", f"Bomba en marcha y nivel estable en {nivel:.1f} cm: la entrada equilibra la salida.",
               "Sin accion.")


# ----------------------------------------------------------------------------- conocimiento
GRAFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento", "grafo_mcn09.json")

# Cadena causal (aristas del grafo) que explica cada diagnostico; se resalta en el lienzo.
CADENAS: dict[str, list[tuple[str, str]]] = {
    "SELECTOR_EN_0": [("selector", "pid")],
    "REMOTO_SIN_SUPERVISOR": [("selector", "pid"), ("hmi", "pid"), ("pid", "variador")],
    "TANQUE1_NIVEL_BAJO": [("tanque_t1", "bomba"), ("interruptor_nivel_t1", "bomba")],
    "APERTURA_INICIAL_VALVULA": [("valvula", "tanque_t2")],
    "BOMBA_DETENIDA": [("pulsadores", "bomba"), ("bomba", "tanque_t2")],
    "LLENANDO": [("potenciometro", "variador"), ("variador", "bomba"), ("bomba", "tanque_t2"),
                 ("sensor_ultrasonico", "tanque_t2")],
    "VACIANDO_CON_BOMBA": [("bomba", "tanque_t2"), ("valvula", "tanque_t2"), ("tanque_t2", "tanque_t1")],
    "NIVEL_ESTABLE": [("bomba", "tanque_t2"), ("valvula", "tanque_t2")],
}


def _grafo() -> dict:
    try:
        with open(GRAFO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"nodos": {}, "relaciones": []}


def _rel(g: dict, de: str, a: str) -> dict | None:
    return next((r for r in g.get("relaciones", []) if r["de"] == de and r["a"] == a), None)


def _cadena(g: dict, pares: list[tuple[str, str]]) -> list[str]:
    out = []
    for de, a in pares:
        r = _rel(g, de, a)
        if r and de in g["nodos"] and a in g["nodos"]:
            out.append(f"{g['nodos'][de]['nombre']} --{r['rel']}--> {g['nodos'][a]['nombre']}"
                       + (f"  ({r['nota']})" if r.get("nota") else ""))
    return out


def _aristas(g: dict, pares: list[tuple[str, str]]) -> list[dict]:
    return [{"de": de, "a": a, "rel": r["rel"]} for de, a in pares if (r := _rel(g, de, a))]


@mcp.tool(annotations=SOLO_LECTURA)
def consultar_grafo(entidad: str | None = None) -> dict:
    """Knowledge graph del modulo de nivel: tanques, bomba, variador, sensor, valvula, mandos y control con sus
    variables UNS y relaciones (alimenta, impulsa, mide, controla, habilita, descarga_en...). Sin 'entidad' devuelve
    el grafo completo; con 'entidad' (p. ej. 'tanque_t2', 'bomba') sus relaciones y lo que influye aguas arriba."""
    g = _grafo()
    if not entidad:
        return {"modelo": g.get("modelo"), "nodos": g["nodos"], "relaciones": g["relaciones"],
                "capacidad_observada": g.get("capacidad_observada")}
    e = entidad.strip().lower()
    if e not in g["nodos"]:
        raise ToolError(f"Entidad '{entidad}' no existe. Opciones: {', '.join(g['nodos'])}")
    vistos, cola, arriba = {e}, [e], []
    while cola:
        x = cola.pop(0)
        for r in g["relaciones"]:
            if r["a"] == x and r["de"] not in vistos and r["rel"] != "mide":
                vistos.add(r["de"]); cola.append(r["de"]); arriba.append(f"{r['de']} --{r['rel']}--> {x}")
    return {"entidad": e, **g["nodos"][e], "relaciones_entrada": [r for r in g["relaciones"] if r["a"] == e],
            "relaciones_salida": [r for r in g["relaciones"] if r["de"] == e], "aguas_arriba": arriba}


# ----------------------------------------------------------------------------- arranque
def _probar() -> None:
    pruebas = [
        ("listar_variables", lambda: listar_variables()),
        ("obtener_estado_plc", lambda: obtener_estado_plc()),
        ("obtener_lectura", lambda: obtener_lectura(["nivel/cm", "estado/bomba_marcha"])),
        ("consultar_historial", lambda: consultar_historial("nivel/cm", minutos=120, puntos_max=10)),
        ("comparar_con_rango", lambda: comparar_con_rango()),
        ("diagnosticar_nivel", lambda: diagnosticar_nivel()),
        ("diagnosticar_nivel @12:57:20", lambda: diagnosticar_nivel("2026-10-20T12:57:20")),
    ]
    for nombre, f in pruebas:
        print(f"\n===== {nombre} =====")
        try:
            print(json.dumps(f(), ensure_ascii=False, indent=2, default=str)[:2500])
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor MCP solo lectura del modulo de nivel MCN-09")
    ap.add_argument("--probar", action="store_true", help="ejecuta todas las herramientas una vez y termina")
    if ap.parse_args().probar:
        _probar()
    else:
        mcp.run()
