"""
Servidor MCP SOLO LECTURA del modulo de control de presion MCP-09/001 (laboratorio USS).  v1.0

PAC NI Compact FieldPoint cFP-2200 (LabVIEW RT 8.6). Datos del UNS guardados en TimescaleDB por el
servicio 'ingestor-presion' con prefijo 'presion-mcp09/' (p. ej. 'presion-mcp09/presion/psi').
- Se conecta con el rol mcp_lector (solo SELECT) y abre cada sesion en modo read-only.
- No tiene ninguna ruta hacia el PAC.
- Las herramientas aceptan los nombres con o sin prefijo ('presion/psi' o 'presion-mcp09/presion/psi')
  y devuelven los nombres sin prefijo.

Prueba manual:
    set MCP_DSN=postgresql://mcp_lector:TU_CLAVE@localhost:5432/uns
    python mcp_servidor/servidor_mcp_presion.py --probar
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
    """Si no hay MCP_DSN, arma la conexion con MCP_READER_PASSWORD del .env del historiador."""
    clave = os.getenv("MCP_READER_PASSWORD")
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not clave and os.path.exists(env):
        with open(env, encoding="utf-8", errors="replace") as f:
            for linea in f:
                if linea.strip().startswith("MCP_READER_PASSWORD="):
                    clave = linea.split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://mcp_lector:{clave or 'lector_cambiar'}@localhost:5432/uns"


DSN = os.getenv("MCP_DSN") or _dsn_por_defecto()
BASE = os.getenv("UNS_BASE_PRESION", "uss/campus/lab-automatizacion/sl01la07/presion-mcp09")
PREFIJO = "presion-mcp09/"
HEARTBEAT_MAX_S = float(os.getenv("HEARTBEAT_MAX_S", "30"))
VALOR_MAX_S = float(os.getenv("VALOR_MAX_S", "90"))
TZ_LIMA = timezone(timedelta(hours=-5))
VARIABLE_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)+$")
MAX_MINUTOS = 60 * 24 * 31
SOLO_LECTURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# Datos del proceso (manual Inducontrol MCP-09/001 + pruebas del 21-oct-2026)
RANGO_TRABAJO_PSI = (3.0, 40.0)        # rango de operacion del manual
FONDO_ESCALA_PSI = 87.0                # transmisor 0-6 bar
TOLERANCIA_SP_PSI = 1.0                # |error| menor = en setpoint
UMBRAL_TENDENCIA_PSI_MIN = 0.5         # |pendiente| menor = presion estable
CV_SATURADA_V = 9.5                    # salida del PID practicamente al maximo (10 V)
SATURACION_MIN_S = 20.0                # tiempo minimo saturado para declarar que el actuador no responde
VENTANA_S = 30

INSTRUCCIONES = """Servidor de SOLO LECTURA del modulo de control de presion MCP-09/001 (PAC National Instruments
cFP-2200 con LabVIEW Real-Time, laboratorio de automatizacion USS). Datos del Unified Namespace en TimescaleDB.
Reglas para el agente:
- Nunca inventes valores, unidades ni limites: usa solo lo que devuelven las herramientas.
- Menciona siempre unidad, hora o periodo y si el dato esta VIGENTE o DESACTUALIZADO.
- Comunica las advertencias (rango del fabricante sin validar, variable en hipotesis, manometro averiado...).
- No puedes modificar el proceso: si piden arrancar, parar o cambiar el setpoint, explica que es solo lectura.
Contexto del proceso: la bomba (variador Altivar 11) lleva agua del tanque T1 al tanque CERRADO T2; al entrar agua
el aire se comprime y la presion sube. La valvula proporcional (0-10 V) descarga T2 hacia T1 y actua como
perturbacion. El transmisor 4-20 mA da 'presion/psi' = (mA-4)/16 x 87 (misma escala que la HMI; el manometro
del modulo esta averiado). Rango de trabajo del manual: 3-40 psi.
Modos: LOCAL = ARRANQUE/PARADA con pulsadores, valvula al 50 % y velocidad fijada en el variador; REMOTO = PID del cFP
con setpoint, Kp, Ti, Td y valvula desde el SCADA de la PC o la HMI. Hallazgo del 21-oct-2026: el Altivar 11 toma la
velocidad de su perilla frontal y NO obedece la salida 0-10 V del PID.
Para preguntas de que esta pasando o por que, usa primero diagnosticar_presion; consultar_grafo describe los
equipos y sus relaciones causales."""

mcp = MCPServer("presion-mcp09", instructions=INSTRUCCIONES, version="1.0")


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
        raise ToolError(f"La variable '{v}' no existe en el historiador del modulo de presion. Usa listar_variables.")
    return completo


def _periodo(minutos: float | None, inicio: str | None, fin: str | None) -> tuple[datetime, datetime]:
    def parse(s: str) -> datetime:
        try:
            t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"Fecha no valida: '{s}'. Usa ISO 8601, p. ej. 2026-10-21T18:52") from None
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
        motivos.append(f"cFP {plc['texto'] if plc else 'sin reportar'}")
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


def _setpoint(u: dict) -> tuple[float | None, str | None]:
    """Setpoint activo: el de la PC si es > 0, si no el de la HMI."""
    pc, hmi = _v(u, "pid/setpoint_pc"), _v(u, "pid/setpoint_hmi")
    if pc and pc > 0:
        return pc, "SCADA PC"
    if hmi and hmi > 0:
        return hmi, "HMI"
    return None, None


def _tendencia(t_ref: datetime | None = None, segundos: float = VENTANA_S) -> dict:
    """Pendiente de la presion (psi/min) por regresion lineal en la ventana."""
    tr = t_ref or _ahora()
    f = _consulta(
        """SELECT count(*) AS n, regr_slope(valor, extract(epoch FROM time)) AS pendiente,
                  avg(valor) AS promedio, min(valor) AS minimo, max(valor) AS maximo
           FROM mediciones WHERE fuente = 'uns' AND variable = %s
             AND time > %s - make_interval(secs => %s) AND time <= %s""",
        (PREFIJO + "presion/psi", tr, segundos, tr))[0]
    p = None if f["pendiente"] is None else float(f["pendiente"]) * 60
    if p is None or f["n"] < 4:
        estado = "SIN_DATOS_SUFICIENTES"
    elif p > UMBRAL_TENDENCIA_PSI_MIN:
        estado = "SUBIENDO"
    elif p < -UMBRAL_TENDENCIA_PSI_MIN:
        estado = "BAJANDO"
    else:
        estado = "ESTABLE"
    return {"ventana_s": segundos, "muestras": f["n"], "tendencia": estado, "pendiente_psi_min": _num(p, 2),
            "presion_promedio_ventana_psi": _num(f["promedio"], 2)}


def _segundos_saturado(t_ref: datetime | None = None) -> float | None:
    """Segundos que lleva la salida del PID por encima de CV_SATURADA_V (None si no esta saturada)."""
    tr = t_ref or _ahora()
    var = PREFIJO + "pid/cv"
    ult = _consulta("""SELECT valor FROM mediciones WHERE fuente = 'uns' AND variable = %s AND time <= %s
                       ORDER BY time DESC LIMIT 1""", (var, tr))
    if not ult or ult[0]["valor"] < CV_SATURADA_V:
        return None
    desde = _consulta(
        """SELECT min(time) AS t FROM mediciones WHERE fuente = 'uns' AND variable = %(v)s AND time <= %(t)s
             AND valor >= %(c)s AND time > coalesce((SELECT max(time) FROM mediciones WHERE fuente = 'uns'
                 AND variable = %(v)s AND time <= %(t)s AND valor < %(c)s), '-infinity')""",
        {"v": var, "t": tr, "c": CV_SATURADA_V})[0]["t"]
    return (tr - desde).total_seconds() if desde else None


# ----------------------------------------------------------------------------- herramientas
@mcp.tool(annotations=SOLO_LECTURA)
def listar_variables() -> dict:
    """Lista las variables del modulo de presion en el historiador (nombre UNS, variable NI-PSP de origen, unidad,
    descripcion, si esta confirmada o en hipotesis) con su ultimo dato en vivo."""
    filas = _consulta(
        """WITH u AS (SELECT DISTINCT ON (variable) variable, time FROM mediciones
                      WHERE fuente = 'uns' AND variable LIKE %(p)s ORDER BY variable, time DESC),
                todas AS (SELECT variable FROM variables WHERE variable LIKE %(p)s UNION SELECT variable FROM u)
           SELECT t.variable, v.tag_plc, v.direccion, v.unidad, v.descripcion, u.time AS ultimo_dato_vivo
           FROM todas t LEFT JOIN variables v USING (variable) LEFT JOIN u USING (variable)
           ORDER BY t.variable""", {"p": PREFIJO + "%"})
    return {"base_uns": f"{BASE}/funcional/",
            "variables": [{**f, "variable": _corto(f["variable"]), "ultimo_dato_vivo": _iso(f["ultimo_dato_vivo"])}
                          for f in filas],
            "nota": "Usa los nombres tal cual (p. ej. 'presion/psi'). 'direccion' es la variable compartida del cFP "
                    "(DATOS_PAC/..., pid/..., FP/3AIO/00)."}


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_lectura(variables: list[str]) -> dict:
    """Ultimo valor en vivo de una o varias variables (maximo 20) con unidad, hora, antiguedad y si esta
    VIGENTE o DESACTUALIZADO. Ejemplo: ["presion/psi", "estado/sistema_funcionando"]."""
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
                       "origen_cfp": f["direccion"], "descripcion": f["descripcion"]})
    return {"consultado": _iso(ahora), "enlace": enlace, "lecturas": salida}


ESTADO_VARS = ["estado/selector_remoto", "estado/selector_local", "estado/sistema_funcionando",
               "estado/bomba_habilitada", "estado/alarma_nivel_bajo", "estado/alarma_nivel_alto",
               "estado/presostato", "presion/psi", "presion/transmisor_ma", "bomba/salida_variador",
               "valvula/salida", "pid/setpoint_pc", "pid/setpoint_hmi", "pid/cv", "pid/kp", "pid/ti", "pid/td"]


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_estado_plc() -> dict:
    """Estado general del modulo de presion: conexion del conector y del cFP, modo (LOCAL/REMOTO), sistema en marcha,
    presion actual y su tendencia, setpoint y salida del PID, valvula, parametros PID y alarmas."""
    enlace = _estado_enlace()
    u = _ultimos(ESTADO_VARS)
    psi = _v(u, "presion/psi")
    sp, origen_sp = _setpoint(u)
    valv = _v(u, "valvula/salida")
    advertencias = list(enlace["motivos"])
    if psi is not None and psi > RANGO_TRABAJO_PSI[1]:
        advertencias.append(f"Presion {psi:.1f} psi por encima del rango de trabajo del fabricante (3-40 psi)")
    if _b(u, "estado/alarma_nivel_bajo"):
        advertencias.append("Alarma de NIVEL BAJO en T1 activa")
    if _b(u, "estado/presostato"):
        advertencias.append("Presostato activo (significado sin confirmar: posible sobrepresion)")
    advertencias.append("El manometro del modulo esta averiado: la referencia de presion es el transmisor (= HMI).")
    return {
        "consultado": _iso(_ahora()), "enlace": enlace, "modo": _modo(u),
        "sistema_funcionando": _b(u, "estado/sistema_funcionando"),
        "variador_habilitado": _b(u, "estado/bomba_habilitada"),
        "presion_psi": _num(psi, 2), "transmisor_ma": _num(_v(u, "presion/transmisor_ma"), 3),
        "hora_presion": _iso(u["presion/psi"]["time"]) if "presion/psi" in u else None,
        "tendencia_presion": _tendencia(),
        "setpoint_psi": _num(sp, 2), "origen_setpoint": origen_sp,
        "salida_pid_v": _num(_v(u, "pid/cv"), 2), "consigna_variador_v": _num(_v(u, "bomba/salida_variador"), 2),
        "valvula_v": _num(valv, 2), "valvula_pct": _num(valv * 10, 0) if valv is not None else None,
        "pid": {"kp": _v(u, "pid/kp"), "ti": _v(u, "pid/ti"), "td": _v(u, "pid/td")},
        "alarma_nivel_bajo_t1": _b(u, "estado/alarma_nivel_bajo"),
        "alarma_nivel_alto_t1": _b(u, "estado/alarma_nivel_alto"),
        "presostato": _b(u, "estado/presostato"),
        "advertencias": advertencias,
    }


@mcp.tool(annotations=SOLO_LECTURA)
def consultar_historial(variable: str = "presion/psi", minutos: float | None = 60, inicio: str | None = None,
                        fin: str | None = None, puntos_max: int = 60) -> dict:
    """Historial de una variable: estadisticas (promedio, minimo, maximo, desviacion, inicial, final, variacion)
    y una serie resumida de hasta 'puntos_max' puntos. Periodo: ultimos 'minutos' o 'inicio'/'fin' ISO 8601
    (hora de Lima si no tiene zona)."""
    completo = _validar_variable(variable)
    t0, t1 = _periodo(minutos, inicio, fin)
    puntos_max = max(5, min(int(puntos_max), 500))
    st = _consulta(
        """SELECT count(*) AS n, avg(valor) AS promedio, min(valor) AS minimo, max(valor) AS maximo,
                  stddev_samp(valor) AS desviacion, min(time) AS primero, max(time) AS ultimo,
                  (array_agg(valor ORDER BY time))[1] AS valor_inicial,
                  (array_agg(valor ORDER BY time DESC))[1] AS valor_final, max(unidad) AS unidad
           FROM mediciones WHERE variable = %s AND fuente = 'uns' AND time >= %s AND time < %s""",
        (completo, t0, t1))[0]
    resp = {"variable": _corto(completo), "periodo": {"inicio": _iso(t0), "fin": _iso(t1)},
            "unidad": st["unidad"], "muestras": st["n"], "advertencias": []}
    if not st["n"]:
        resp["advertencias"].append("No hay datos en ese periodo")
        ult = _consulta("SELECT max(time) AS t FROM mediciones WHERE variable = %s AND fuente = 'uns'",
                        (completo,))[0]["t"]
        resp["ultimo_dato_disponible"] = _iso(ult)
        return resp
    paso = max(1, math.ceil((t1 - t0).total_seconds() / puntos_max))
    serie = _consulta(
        """SELECT date_bin(make_interval(secs => %s), time, %s) AS t, avg(valor) AS v, min(valor) AS mn, max(valor) AS mx
           FROM mediciones WHERE variable = %s AND fuente = 'uns' AND time >= %s AND time < %s
           GROUP BY 1 ORDER BY 1""", (paso, t0, completo, t0, t1))
    resp.update({
        "estadisticas": {"promedio": _num(st["promedio"]), "minimo": _num(st["minimo"]), "maximo": _num(st["maximo"]),
                         "desviacion": _num(st["desviacion"]), "valor_inicial": _num(st["valor_inicial"]),
                         "valor_final": _num(st["valor_final"]),
                         "variacion": _num(st["valor_final"] - st["valor_inicial"]),
                         "primer_dato": _iso(st["primero"]), "ultimo_dato": _iso(st["ultimo"])},
        "intervalo_serie_s": paso,
        "serie": [{"t": _iso(f["t"]), "promedio": _num(f["v"]), "min": _num(f["mn"]), "max": _num(f["mx"])}
                  for f in serie]})
    resp["advertencias"].append("El conector publica por cambio o cada 60 s: muestras no equiespaciadas.")
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def comparar_con_rango(variable: str = "presion/psi", minutos: float = 5) -> dict:
    """Compara el valor actual y los ultimos 'minutos' de una variable con su rango registrado (para 'presion/psi':
    3-40 psi, rango del fabricante). Indica si esta dentro, % de muestras fuera y quien valido el rango."""
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
    if v is not None and v < r["minimo"]:
        resp["advertencias"].append("Por debajo de 3 psi suele significar que la bomba no esta presurizando "
                                    "(sistema detenido o variador sin velocidad).")
    if actual.get("estado") != "VIGENTE":
        resp["advertencias"].append(f"La lectura actual esta {actual.get('estado')}: {actual.get('motivo')}")
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def diagnosticar_presion(momento: str | None = None) -> dict:
    """Diagnostico del modulo de presion con reglas sobre el estado y los ultimos 30 s. Devuelve UN diagnostico
    principal (SIN_DATOS, SELECTOR_EN_0, SISTEMA_DETENIDO, MANUAL_EN_MARCHA, REMOTO_SIN_SETPOINT,
    ACTUADOR_NO_RESPONDE, SUBIENDO_A_SETPOINT, EN_SETPOINT, SOBRE_SETPOINT o FUERA_DE_SETPOINT), hallazgos
    secundarios, evidencia numerica (presion, setpoint, error, salida del PID, tendencia en psi/min, tiempo
    saturado) y una recomendacion. Usala primero para preguntas de que esta pasando o por que. Con 'momento'
    (ISO 8601, hora de Lima) reproduce el diagnostico en el pasado."""
    t_ref = None
    if momento:
        try:
            t_ref = datetime.fromisoformat(momento.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"momento no valido: '{momento}'. Usa ISO 8601, p. ej. 2026-10-21T18:55:00") from None
        if t_ref.tzinfo is None:
            t_ref = t_ref.replace(tzinfo=TZ_LIMA)
        if t_ref > _ahora():
            raise ToolError("momento no puede estar en el futuro")
        enlace = {"datos_en_vivo": True, "motivos": []}
    else:
        enlace = _estado_enlace()
    u = _ultimos(ESTADO_VARS, t_ref)
    modo, marcha = _modo(u), _b(u, "estado/sistema_funcionando")
    psi, cv = _v(u, "presion/psi"), _v(u, "pid/cv")
    sp, origen_sp = _setpoint(u)
    err = (sp - psi) if (sp is not None and psi is not None) else None
    tend = _tendencia(t_ref)
    sat_s = _segundos_saturado(t_ref)
    valv = _v(u, "valvula/salida")
    evid = {"modo": modo, "sistema_funcionando": marcha, "variador_habilitado": _b(u, "estado/bomba_habilitada"),
            "presion_psi": _num(psi, 2), "setpoint_psi": _num(sp, 2), "origen_setpoint": origen_sp,
            "error_psi": _num(err, 2), "salida_pid_v": _num(cv, 2), "segundos_pid_saturado": _num(sat_s, 0),
            "valvula_pct": _num(valv * 10, 0) if valv is not None else None, **tend}
    resp = {"consultado": _iso(_ahora()), "momento_evaluado": _iso(t_ref or _ahora()),
            "modo_consulta": "reproduccion historica" if t_ref else "en vivo", "evidencia": evid}
    sec = []
    if psi is not None and psi > RANGO_TRABAJO_PSI[1]:
        sec.append({"hallazgo": "SOBRE_RANGO_DE_TRABAJO", "detalle": f"Presion {psi:.1f} psi sobre 40 psi "
                    "(limite de trabajo del fabricante)."})
    if _b(u, "estado/presostato"):
        sec.append({"hallazgo": "PRESOSTATO_ACTIVO", "detalle": "El presostato esta activo (logica sin confirmar)."})
    if _b(u, "estado/alarma_nivel_bajo"):
        sec.append({"hallazgo": "NIVEL_BAJO_T1", "detalle": "Alarma de nivel bajo en el tanque T1."})
    if marcha and modo == "LOCAL" and psi is not None and psi < RANGO_TRABAJO_PSI[0]:
        sec.append({"hallazgo": "PRESION_BAJO_RANGO", "detalle": f"En marcha con solo {psi:.2f} psi (< 3 psi): la "
                    "velocidad fijada en el variador es baja o la valvula esta muy abierta."})

    def fin(diag, explicacion, recomendacion):
        pares = list(CADENAS.get(diag, []))
        g = _grafo()
        resp.update({"diagnostico": diag, "explicacion": explicacion, "hallazgos_secundarios": sec,
                     "cadena_causal": _cadena(g, pares), "aristas_causales": _aristas(g, pares),
                     "recomendacion": recomendacion})
        return resp

    pend = tend["pendiente_psi_min"]
    if not enlace["datos_en_vivo"]:
        return fin("SIN_DATOS", "No hay datos en vivo: " + "; ".join(enlace["motivos"]),
                   "Revisar el conector DataSocket de la VM Windows 7 y la conexion con el cFP (192.168.114.8).")
    if modo == "SELECTOR_EN_0":
        return fin("SELECTOR_EN_0", "Ninguna posicion del selector CONTROL esta activa.",
                   "Poner el selector en LOCAL o REMOTO.")
    if not marcha:
        txt = "El sistema esta detenido (sistema funcionando = 0)"
        rec = ("En REMOTO: pulsar INICIO en el SCADA o la HMI." if modo == "REMOTO"
               else "En LOCAL: pulsar ARRANQUE MANUAL.")
        return fin("SISTEMA_DETENIDO", txt + (f"; presion {psi:.2f} psi." if psi is not None else "."), rec)
    if modo == "LOCAL":
        return fin("MANUAL_EN_MARCHA",
                   f"Modo LOCAL en marcha: presion {psi:.2f} psi ({tend['tendencia'].lower()}"
                   + (f", {pend:+.2f} psi/min" if pend is not None else "") + "). La valvula queda al 50 % y la "
                   "velocidad la fija la perilla frontal del variador; el PID no actua.",
                   "Para subir la presion aumentar la velocidad en el variador; para control automatico usar REMOTO.")
    # --- REMOTO en marcha ---
    if sp is None:
        return fin("REMOTO_SIN_SETPOINT", "REMOTO en marcha pero el supervisor no fijo un setpoint (0 o sin valor).",
                   "Fijar el setpoint en el SCADA de la PC o en la HMI.")
    if (sat_s is not None and sat_s >= SATURACION_MIN_S and err is not None and err > 2 * TOLERANCIA_SP_PSI
            and (pend is None or pend < UMBRAL_TENDENCIA_PSI_MIN)):
        return fin("ACTUADOR_NO_RESPONDE",
                   f"El PID pide la velocidad maxima ({cv:.1f} V) desde hace {sat_s:.0f} s, pero la presion sigue en "
                   f"{psi:.2f} psi frente a un setpoint de {sp:.1f} psi y no sube. El lazo esta abierto: el variador no "
                   "obedece la consigna analogica (el 21-oct-2026 se comprobo que el Altivar 11 toma la velocidad de su "
                   "perilla frontal), o la bomba no impulsa agua (aire, T1 vacio, valvula de salida muy abierta).",
                   "Detener la prueba y que el responsable revise la configuracion de consigna del Altivar 11 (entrada "
                   "AI1 0-10 V). Al reintentar, usar un setpoint bajo y Ti mayor para evitar la saturacion.")
    if abs(err) <= TOLERANCIA_SP_PSI:
        return fin("EN_SETPOINT", f"Presion {psi:.2f} psi en el setpoint {sp:.1f} psi (error {err:+.2f} psi).",
                   "Sin accion.")
    if err > 0 and tend["tendencia"] == "SUBIENDO":
        return fin("SUBIENDO_A_SETPOINT", f"La presion sube hacia el setpoint: {psi:.2f} de {sp:.1f} psi "
                   f"({pend:+.2f} psi/min).", "Esperar a que el lazo se estabilice.")
    if err < 0:
        return fin("SOBRE_SETPOINT", f"Presion {psi:.2f} psi por encima del setpoint {sp:.1f} psi.",
                   "Revisar sobreimpulso del PID o abrir mas la valvula (perturbacion).")
    return fin("FUERA_DE_SETPOINT", f"Presion {psi:.2f} psi por debajo del setpoint {sp:.1f} psi sin subir "
               f"(salida del PID {cv if cv is not None else 'sin dato'} V).", "Vigilar la salida del PID y el variador.")


# ----------------------------------------------------------------------------- conocimiento
GRAFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento", "grafo_mcp09.json")

CADENAS: dict[str, list[tuple[str, str]]] = {
    "SELECTOR_EN_0": [("selector", "pid")],
    "SISTEMA_DETENIDO": [("pulsadores", "bomba"), ("supervisor", "pid")],
    "MANUAL_EN_MARCHA": [("potenciometro_variador", "variador"), ("variador", "bomba"), ("bomba", "tanque_t2"),
                         ("transmisor", "tanque_t2")],
    "REMOTO_SIN_SETPOINT": [("supervisor", "pid")],
    "ACTUADOR_NO_RESPONDE": [("pid", "variador"), ("potenciometro_variador", "variador"),
                             ("variador", "bomba"), ("bomba", "tanque_t2")],
    "SUBIENDO_A_SETPOINT": [("pid", "variador"), ("variador", "bomba"), ("bomba", "tanque_t2")],
    "EN_SETPOINT": [("pid", "variador"), ("bomba", "tanque_t2"), ("valvula", "tanque_t2")],
    "SOBRE_SETPOINT": [("pid", "variador"), ("valvula", "tanque_t2")],
    "FUERA_DE_SETPOINT": [("pid", "variador"), ("variador", "bomba")],
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
    """Knowledge graph del modulo de presion: tanques, bomba, variador, transmisor, valvula, presostato, mandos,
    PID y supervisor con sus variables UNS y relaciones (alimenta, acciona, presuriza, mide, controla...). Sin
    'entidad' devuelve el grafo completo; con 'entidad' (p. ej. 'tanque_t2', 'variador') sus relaciones y lo que
    influye aguas arriba."""
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
        ("obtener_lectura", lambda: obtener_lectura(["presion/psi", "estado/sistema_funcionando"])),
        ("consultar_historial", lambda: consultar_historial("presion/psi", minutos=120, puntos_max=10)),
        ("comparar_con_rango", lambda: comparar_con_rango()),
        ("diagnosticar_presion", lambda: diagnosticar_presion()),
        ("diagnosticar_presion @18:30:30 (LOCAL en marcha)", lambda: diagnosticar_presion("2026-10-21T18:30:30")),
        ("diagnosticar_presion @18:55:00 (REMOTO, PID saturado)", lambda: diagnosticar_presion("2026-10-21T18:55:00")),
    ]
    for nombre, f in pruebas:
        print(f"\n===== {nombre} =====")
        try:
            print(json.dumps(f(), ensure_ascii=False, indent=2, default=str)[:2500])
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor MCP solo lectura del modulo de presion MCP-09")
    ap.add_argument("--probar", action="store_true", help="ejecuta todas las herramientas una vez y termina")
    if ap.parse_args().probar:
        _probar()
    else:
        mcp.run()
