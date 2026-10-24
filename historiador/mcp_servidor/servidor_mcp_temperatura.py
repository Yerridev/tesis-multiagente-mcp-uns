"""
Servidor MCP SOLO LECTURA del modulo de control de temperatura MCT-09/001 (laboratorio USS).  v1.0

PLC Schneider Twido TWDLCAE40DRF (Modbus TCP 192.168.114.10). Datos del UNS guardados en TimescaleDB por el
servicio 'ingestor-temperatura' con prefijo 'temperatura-mct09/' (p. ej. 'temperatura-mct09/temperatura/principal_c').
- Se conecta con el rol mcp_lector (solo SELECT) y abre cada sesion en modo read-only.
- No tiene ninguna ruta hacia el PLC.
- Las herramientas aceptan los nombres con o sin prefijo y devuelven los nombres sin prefijo.

Prueba manual:
    set MCP_DSN=postgresql://mcp_lector:TU_CLAVE@localhost:5432/uns
    python mcp_servidor/servidor_mcp_temperatura.py --probar
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
BASE = os.getenv("UNS_BASE_TEMPERATURA", "uss/campus/lab-automatizacion/sl01la07/temperatura-mct09")
PREFIJO = "temperatura-mct09/"
HEARTBEAT_MAX_S = float(os.getenv("HEARTBEAT_MAX_S", "30"))
VALOR_MAX_S = float(os.getenv("VALOR_MAX_S", "90"))
TZ_LIMA = timezone(timedelta(hours=-5))
VARIABLE_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)+$")
MAX_MINUTOS = 60 * 24 * 31
SOLO_LECTURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# Datos del proceso (manual Inducontrol MCT-09/001 + pruebas del 23-oct-2026)
RANGO_TRABAJO_C = (15.0, 50.0)         # rango de operacion optimo del manual
LIMITE_ALARMA_C = 60.0                 # por encima: riesgo para sensores/juntas; detener
TOLERANCIA_SP_C = 1.0                  # |error| menor = en setpoint (la senal tiene ruido de +-1 C)
VENTANA_S = 180                        # ventana de la tendencia (la temperatura cambia lento)
UMBRAL_TENDENCIA_C_MIN = 0.05          # |pendiente| menor = estable
UMBRAL_SIN_ORDEN_C_MIN = 0.10          # sube sin orden del PLC durante la ventana larga = rele en falla
VENTANA_SIN_ORDEN_S = 300
SALIDA_SATURADA_PCT = 95.0             # PID practicamente al maximo
SATURACION_MIN_S = 600.0               # 10 min saturado sin calentar = la potencia no llega al agua

INSTRUCCIONES = """Servidor de SOLO LECTURA del modulo de control de temperatura MCT-09/001 (PLC Schneider Twido,
laboratorio de automatizacion USS). Datos del Unified Namespace en TimescaleDB.
Reglas para el agente:
- Nunca inventes valores, unidades ni limites: usa solo lo que devuelven las herramientas.
- Menciona siempre unidad, hora o periodo y si el dato esta VIGENTE o DESACTUALIZADO.
- Comunica las advertencias (escala sin contrastar con termometro, rango del fabricante sin validar, hipotesis...).
- No puedes modificar el proceso: si piden arrancar, parar o cambiar el setpoint, explica que es solo lectura.
Contexto del proceso: el tanque PRINCIPAL (T2, inferior, 125 L) tiene una resistencia calefactora que el PID del
PLC modula por PWM a traves de un rele de estado solido. La bomba (Altivar 11) recircula el agua hacia el tanque de
ENFRIAMIENTO (T1, superior) con serpentin y enfriador, que entra cuando la temperatura supera el setpoint.
Temperaturas: Pt100 + transmisor 4-20 mA, C = cuentas*100/4095 (escala del SCADA original), media movil de 10 s;
la senal tiene ruido de +-1 C con la bomba en marcha. Rango de operacion del fabricante: 15-50 C.
Modos: selector CONTROLADOR en PC (REMOTO, SCADA de la PC) o HMI (LOCAL, pantalla del tablero). El lazo solo
arranca si ambos tanques tienen el agua entre sus interruptores de nivel bajo y alto.
Seguridad (23-oct-2026): el rele de estado solido (FOTEK, sin disipador) calento el agua SIN orden del PLC; si la
temperatura sube con el lazo detenido es una falla electrica, no del control.
Para preguntas de que esta pasando o por que, usa primero diagnosticar_temperatura; consultar_grafo describe los
equipos y sus relaciones causales."""

mcp = MCPServer("temperatura-mct09", instructions=INSTRUCCIONES, version="1.0")


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
        raise ToolError(f"La variable '{v}' no existe en el historiador del modulo de temperatura. Usa listar_variables.")
    return completo


def _periodo(minutos: float | None, inicio: str | None, fin: str | None) -> tuple[datetime, datetime]:
    def parse(s: str) -> datetime:
        try:
            t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"Fecha no valida: '{s}'. Usa ISO 8601, p. ej. 2026-10-23T18:00") from None
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
        motivos.append(f"PLC Twido {plc['texto'] if plc else 'sin reportar'}")
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


def _tendencia(t_ref: datetime | None = None, segundos: float = VENTANA_S,
               variable: str = "temperatura/principal_c") -> dict:
    """Pendiente de la temperatura (C/min) por regresion lineal en la ventana."""
    tr = t_ref or _ahora()
    f = _consulta(
        """SELECT count(*) AS n, regr_slope(valor, extract(epoch FROM time)) AS pendiente,
                  avg(valor) AS promedio, min(valor) AS minimo, max(valor) AS maximo
           FROM mediciones WHERE fuente = 'uns' AND variable = %s
             AND time > %s - make_interval(secs => %s) AND time <= %s""",
        (PREFIJO + variable, tr, segundos, tr))[0]
    p = None if f["pendiente"] is None else float(f["pendiente"]) * 60
    if p is None or f["n"] < 4:
        estado = "SIN_DATOS_SUFICIENTES"
    elif p > UMBRAL_TENDENCIA_C_MIN:
        estado = "SUBIENDO"
    elif p < -UMBRAL_TENDENCIA_C_MIN:
        estado = "BAJANDO"
    else:
        estado = "ESTABLE"
    return {"ventana_s": segundos, "muestras": f["n"], "tendencia": estado, "pendiente_c_min": _num(p, 3),
            "temperatura_promedio_ventana_c": _num(f["promedio"], 2)}


def _segundos_en(variable: str, condicion_sql: str, umbral: float, t_ref: datetime | None = None) -> float | None:
    """Segundos que una variable lleva cumpliendo 'valor <cond> umbral' (None si hoy no la cumple)."""
    tr = t_ref or _ahora()
    var = PREFIJO + variable
    cumple = f"valor {condicion_sql} %(u)s"
    ult = _consulta(f"""SELECT ({cumple}) AS ok FROM mediciones WHERE fuente = 'uns' AND variable = %(v)s
                        AND time <= %(t)s ORDER BY time DESC LIMIT 1""", {"v": var, "t": tr, "u": umbral})
    if not ult or not ult[0]["ok"]:
        return None
    desde = _consulta(
        f"""SELECT min(time) AS t FROM mediciones WHERE fuente = 'uns' AND variable = %(v)s AND time <= %(t)s
              AND ({cumple}) AND time > coalesce((SELECT max(time) FROM mediciones WHERE fuente = 'uns'
                  AND variable = %(v)s AND time <= %(t)s AND NOT ({cumple})), '-infinity')""",
        {"v": var, "t": tr, "u": umbral})[0]["t"]
    return (tr - desde).total_seconds() if desde else None


# ----------------------------------------------------------------------------- herramientas
@mcp.tool(annotations=SOLO_LECTURA)
def listar_variables() -> dict:
    """Lista las variables del modulo de temperatura en el historiador (nombre UNS, tag, direccion Modbus del Twido,
    unidad, descripcion, si esta confirmada o en hipotesis) con su ultimo dato en vivo."""
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
            "nota": "Usa los nombres tal cual (p. ej. 'temperatura/principal_c'). 'direccion' es la memoria del Twido "
                    "(%MW = registro, %M = bit). Los historicos del SCADA 2009-2011 estan con fuente 'lvm'."}


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_lectura(variables: list[str]) -> dict:
    """Ultimo valor en vivo de una o varias variables (maximo 20) con unidad, hora, antiguedad y si esta
    VIGENTE o DESACTUALIZADO. Ejemplo: ["temperatura/principal_c", "estado/sistema_funcionando"]."""
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


ESTADO_VARS = ["estado/selector_remoto", "estado/selector_local", "estado/sistema_funcionando",
               "estado/bomba_marcha", "estado/resistencia_on", "estado/enfriador_on",
               "temperatura/principal_c", "temperatura/enfriador_c", "pid/setpoint_c", "pid/salida_pct",
               "pid/kp", "pid/ti", "pid/td", "bomba/consigna_pct",
               "falla/nivel_principal", "falla/nivel_enfriador", "nivel/principal_alto", "nivel/principal_bajo_ok",
               "nivel/enfriador_alto", "nivel/enfriador_bajo_ok", "mando/lazo_remoto", "mando/lazo_local"]


def _advertencias_fijas() -> list[str]:
    return ["Escala de temperatura (cuentas*100/4095) tomada del SCADA original; falta contraste con termometro.",
            "Rele de estado solido de la resistencia pendiente de revision (23-oct-2026 calento sin orden del PLC)."]


@mcp.tool(annotations=SOLO_LECTURA)
def obtener_estado_plc() -> dict:
    """Estado general del modulo de temperatura: conexion del conector y del PLC, modo (PC=REMOTO / HMI=LOCAL),
    lazo en marcha, temperaturas y su tendencia, setpoint, error, salida del PID, bomba, resistencia, enfriador,
    niveles y fallas que bloquean el arranque."""
    enlace = _estado_enlace()
    u = _ultimos(ESTADO_VARS)
    t, sp = _v(u, "temperatura/principal_c"), _v(u, "pid/setpoint_c")
    advertencias = list(enlace["motivos"])
    if t is not None and t > RANGO_TRABAJO_C[1]:
        advertencias.append(f"Temperatura {t:.1f} C por encima del rango de operacion del fabricante (15-50 C)")
    if _b(u, "falla/nivel_principal") or _b(u, "falla/nivel_enfriador"):
        advertencias.append("Falla de nivel activa: el PLC no deja arrancar el lazo")
    if _b(u, "estado/sistema_funcionando") and (not sp or not _v(u, "pid/kp")):
        advertencias.append("Lazo en marcha con setpoint o Kp en 0: el PLC perdio los parametros (se borran al apagar)")
    advertencias += _advertencias_fijas()
    return {
        "consultado": _iso(_ahora()), "enlace": enlace, "modo": _modo(u),
        "lazo_en_marcha": _b(u, "estado/sistema_funcionando"),
        "temperatura_principal_c": _num(t, 2), "temperatura_enfriador_c": _num(_v(u, "temperatura/enfriador_c"), 2),
        "hora_temperatura": _iso(u["temperatura/principal_c"]["time"]) if "temperatura/principal_c" in u else None,
        "tendencia_temperatura": _tendencia(),
        "setpoint_c": _num(sp, 2), "error_c": _num(sp - t, 2) if (sp is not None and t is not None) else None,
        "salida_pid_pct": _num(_v(u, "pid/salida_pct"), 1),
        "orden_resistencia": _b(u, "estado/resistencia_on"),
        "bomba_en_marcha": _b(u, "estado/bomba_marcha"), "consigna_bomba_pct": _num(_v(u, "bomba/consigna_pct"), 1),
        "enfriador_on": _b(u, "estado/enfriador_on"),
        "pid": {"kp": _v(u, "pid/kp"), "ti": _v(u, "pid/ti"), "td": _v(u, "pid/td")},
        "niveles": {"principal_alto": _b(u, "nivel/principal_alto"), "principal_bajo_ok": _b(u, "nivel/principal_bajo_ok"),
                    "enfriador_alto": _b(u, "nivel/enfriador_alto"), "enfriador_bajo_ok": _b(u, "nivel/enfriador_bajo_ok")},
        "falla_nivel_principal": _b(u, "falla/nivel_principal"), "falla_nivel_enfriador": _b(u, "falla/nivel_enfriador"),
        "advertencias": advertencias,
    }


@mcp.tool(annotations=SOLO_LECTURA)
def consultar_historial(variable: str = "temperatura/principal_c", minutos: float | None = 60, inicio: str | None = None,
                        fin: str | None = None, puntos_max: int = 60, fuente: str = "uns") -> dict:
    """Historial de una variable: estadisticas (promedio, minimo, maximo, desviacion, inicial, final, variacion)
    y una serie resumida de hasta 'puntos_max' puntos. Periodo: ultimos 'minutos' o 'inicio'/'fin' ISO 8601
    (hora de Lima si no tiene zona). fuente='uns' (en vivo, desde 2026) o 'lvm' (SCADA original 2009-2011)."""
    if fuente not in ("uns", "lvm"):
        raise ToolError("fuente debe ser 'uns' o 'lvm'")
    completo = _validar_variable(variable)
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
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def comparar_con_rango(variable: str = "temperatura/principal_c", minutos: float = 5) -> dict:
    """Compara el valor actual y los ultimos 'minutos' de una variable con su rango registrado (para la temperatura
    principal y el setpoint: 15-50 C, rango del fabricante). Indica si esta dentro, % de muestras fuera y quien
    valido el rango."""
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
    if v is not None and v < r["minimo"] and _corto(completo).startswith("temperatura/"):
        resp["advertencias"].append("Por debajo de 15 C es normal con el agua fria de la red: el rango del fabricante "
                                    "es el de operacion del lazo, no un limite de seguridad.")
    if actual.get("estado") != "VIGENTE":
        resp["advertencias"].append(f"La lectura actual esta {actual.get('estado')}: {actual.get('motivo')}")
    return resp


@mcp.tool(annotations=SOLO_LECTURA)
def diagnosticar_temperatura(momento: str | None = None) -> dict:
    """Diagnostico del modulo de temperatura con reglas sobre el estado y la tendencia de los ultimos minutos.
    Devuelve UN diagnostico principal (SIN_DATOS, CALENTAMIENTO_SIN_ORDEN, SOBRE_LIMITE, FALLA_NIVEL,
    SELECTOR_EN_0, SISTEMA_DETENIDO, LAZO_SIN_PARAMETROS, RESISTENCIA_SIN_EFECTO, CALENTANDO_A_SETPOINT,
    EN_SETPOINT, SOBRE_SETPOINT o FUERA_DE_SETPOINT), hallazgos secundarios, evidencia numerica (temperaturas,
    setpoint, error, salida del PID, tendencia en C/min, tiempo saturado) y una recomendacion. Usala primero para
    preguntas de que esta pasando o por que. Con 'momento' (ISO 8601, hora de Lima) reproduce el diagnostico en el
    pasado."""
    t_ref = None
    if momento:
        try:
            t_ref = datetime.fromisoformat(momento.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(f"momento no valido: '{momento}'. Usa ISO 8601, p. ej. 2026-10-23T18:00:00") from None
        if t_ref.tzinfo is None:
            t_ref = t_ref.replace(tzinfo=TZ_LIMA)
        if t_ref > _ahora():
            raise ToolError("momento no puede estar en el futuro")
        enlace = {"datos_en_vivo": True, "motivos": []}
    else:
        enlace = _estado_enlace()
    u = _ultimos(ESTADO_VARS, t_ref)
    modo, marcha = _modo(u), _b(u, "estado/sistema_funcionando")
    t, sp, salida = _v(u, "temperatura/principal_c"), _v(u, "pid/setpoint_c"), _v(u, "pid/salida_pct")
    err = (sp - t) if (sp is not None and t is not None) else None
    tend = _tendencia(t_ref)
    tend_larga = _tendencia(t_ref, VENTANA_SIN_ORDEN_S)
    sat_s = _segundos_en("pid/salida_pct", ">=", SALIDA_SATURADA_PCT, t_ref)
    bomba = _v(u, "bomba/consigna_pct")
    evid = {"modo": modo, "lazo_en_marcha": marcha, "temperatura_c": _num(t, 2),
            "temperatura_enfriador_c": _num(_v(u, "temperatura/enfriador_c"), 2), "setpoint_c": _num(sp, 2),
            "error_c": _num(err, 2), "salida_pid_pct": _num(salida, 1), "segundos_pid_saturado": _num(sat_s, 0),
            "orden_resistencia": _b(u, "estado/resistencia_on"), "bomba_en_marcha": _b(u, "estado/bomba_marcha"),
            "consigna_bomba_pct": _num(bomba, 1), "enfriador_on": _b(u, "estado/enfriador_on"),
            "pendiente_5min_c_min": tend_larga["pendiente_c_min"], **tend}
    resp = {"consultado": _iso(_ahora()), "momento_evaluado": _iso(t_ref or _ahora()),
            "modo_consulta": "reproduccion historica" if t_ref else "en vivo", "evidencia": evid}
    sec = []
    if marcha and _b(u, "estado/bomba_marcha") and bomba is not None and bomba <= 0:
        sec.append({"hallazgo": "BOMBA_EN_CERO", "detalle": "Lazo en marcha con la consigna de la bomba en 0 %: el agua "
                    "no recircula y el sensor de control puede no ver el calor de la resistencia."})
    if err is not None and err < -TOLERANCIA_SP_C and not _b(u, "estado/enfriador_on"):
        sec.append({"hallazgo": "ENFRIADOR_INACTIVO", "detalle": "La temperatura supera el setpoint y el enfriador no "
                    "esta en marcha (hay que habilitarlo con el pulsador HABILITAR ENFRIADOR o desde el SCADA)."})
    if t is not None and RANGO_TRABAJO_C[1] < t <= LIMITE_ALARMA_C:
        sec.append({"hallazgo": "SOBRE_RANGO_DE_TRABAJO", "detalle": f"{t:.1f} C sobre 50 C (rango del fabricante)."})

    def fin(diag, explicacion, recomendacion):
        pares = list(CADENAS.get(diag, []))
        g = _grafo()
        resp.update({"diagnostico": diag, "explicacion": explicacion, "hallazgos_secundarios": sec,
                     "cadena_causal": _cadena(g, pares), "aristas_causales": _aristas(g, pares),
                     "recomendacion": recomendacion, "advertencias": _advertencias_fijas()})
        return resp

    pend, pend5 = tend["pendiente_c_min"], tend_larga["pendiente_c_min"]
    if not enlace["datos_en_vivo"]:
        return fin("SIN_DATOS", "No hay datos en vivo: " + "; ".join(enlace["motivos"]),
                   "Revisar conector_edge_twido.py en la laptop y la red hacia el PLC (192.168.114.10, Modbus 502).")
    if not marcha and pend5 is not None and pend5 >= UMBRAL_SIN_ORDEN_C_MIN and tend_larga["muestras"] >= 4:
        return fin("CALENTAMIENTO_SIN_ORDEN",
                   f"La temperatura sube {pend5:+.2f} C/min en los ultimos 5 min con el lazo DETENIDO (el PLC no "
                   "ordena calentar). La resistencia recibe energia por fuera del control: rele de estado solido en "
                   "cortocircuito (falla vista el 23-oct-2026) o cableado puenteado.",
                   "PELIGRO: bajar la termomagnetica de la resistencia o la llave general y avisar al responsable. "
                   "No operar el modulo hasta revisar el rele de estado solido FOTEK.")
    if t is not None and t > LIMITE_ALARMA_C:
        return fin("SOBRE_LIMITE", f"Temperatura {t:.1f} C por encima de {LIMITE_ALARMA_C:.0f} C.",
                   "Detener el lazo y cortar la resistencia; revisar el setpoint y el rele de estado solido.")
    if _b(u, "falla/nivel_principal") or _b(u, "falla/nivel_enfriador"):
        cual = []
        if _b(u, "nivel/principal_alto"):
            cual.append("nivel ALTO del tanque principal activado")
        if _b(u, "nivel/principal_bajo_ok") is False:
            cual.append("tanque principal bajo el nivel minimo")
        if _b(u, "nivel/enfriador_alto"):
            cual.append("nivel ALTO del tanque de enfriamiento activado")
        if _b(u, "nivel/enfriador_bajo_ok") is False:
            cual.append("tanque de enfriamiento bajo el nivel minimo")
        return fin("FALLA_NIVEL", "El PLC bloquea el lazo por nivel: " + (", ".join(cual) or "falla de nivel activa") + ".",
                   "Ajustar el agua para que quede entre los interruptores de nivel bajo y alto en ambos tanques.")
    if modo == "SELECTOR_EN_0":
        return fin("SELECTOR_EN_0", "El selector CONTROLADOR esta en 0 (ni PC ni HMI).",
                   "Poner el selector en PC (SCADA) o HMI (pantalla del tablero).")
    if not marcha:
        rec = ("En PC: iniciar desde el SCADA MOD_TEMP.exe de la PC .100 (debe estar abierto con el OPC Server)."
               if modo == "REMOTO" else "En HMI: pulsar INICIAR en la pantalla del tablero (requiere el SCADA de la "
               "PC .100 abierto: la HMI escribe al PLC a traves de el).")
        return fin("SISTEMA_DETENIDO", "El lazo esta detenido" + (f"; temperatura {t:.1f} C." if t is not None else "."), rec)
    if not sp or not _v(u, "pid/kp"):
        return fin("LAZO_SIN_PARAMETROS", f"El lazo esta en marcha con setpoint {sp} y Kp {_v(u, 'pid/kp')}: el PLC "
                   "perdio los parametros (se borran al apagarlo) y el PID no calienta.",
                   "Cargar setpoint, Kp, Ti y Td desde el SCADA o la HMI (valores de fabrica Kp 5000, Ti 10, Td 10).")
    if (sat_s is not None and sat_s >= SATURACION_MIN_S and err is not None and err > 2 * TOLERANCIA_SP_C
            and (pend is None or pend < UMBRAL_TENDENCIA_C_MIN)):
        return fin("RESISTENCIA_SIN_EFECTO",
                   f"El PID pide el 100 % de potencia desde hace {sat_s / 60:.0f} min, pero la temperatura sigue en "
                   f"{t:.1f} C frente a {sp:.1f} C y no sube. La potencia no llega al agua: termomagnetica de la "
                   "resistencia abajo, rele de estado solido abierto o resistencia quemada; o la bomba no recircula.",
                   "Revisar la segunda termomagnetica, el LED del rele de estado solido y medir corriente con pinza.")
    if abs(err) <= TOLERANCIA_SP_C:
        return fin("EN_SETPOINT", f"Temperatura {t:.1f} C en el setpoint {sp:.1f} C (error {err:+.1f} C, "
                   f"salida del PID {salida} %).", "Sin accion.")
    if err > 0 and tend["tendencia"] == "SUBIENDO":
        faltan = (err / pend) if pend and pend > 0 else None
        return fin("CALENTANDO_A_SETPOINT", f"El agua se calienta hacia el setpoint: {t:.1f} de {sp:.1f} C "
                   f"({pend:+.2f} C/min" + (f", unos {faltan:.0f} min para llegar" if faltan else "") + ").",
                   "Esperar: el proceso termico es lento (decenas de litros).")
    if err < 0:
        return fin("SOBRE_SETPOINT", f"Temperatura {t:.1f} C por encima del setpoint {sp:.1f} C.",
                   "El PID ya no calienta; para bajar mas rapido habilitar el enfriador.")
    return fin("FUERA_DE_SETPOINT", f"Temperatura {t:.1f} C por debajo del setpoint {sp:.1f} C sin subir "
               f"(salida del PID {salida} %).", "Vigilar la salida del PID y la recirculacion de la bomba.")


# ----------------------------------------------------------------------------- conocimiento
GRAFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento", "grafo_mct09.json")

CADENAS: dict[str, list[tuple[str, str]]] = {
    "CALENTAMIENTO_SIN_ORDEN": [("termomagnetica", "rele_ssr"), ("rele_ssr", "resistencia"),
                                ("resistencia", "tanque_principal")],
    "SOBRE_LIMITE": [("rele_ssr", "resistencia"), ("resistencia", "tanque_principal"), ("sensor_principal", "tanque_principal")],
    "FALLA_NIVEL": [("interruptores_nivel", "pid")],
    "SELECTOR_EN_0": [("selector", "pid")],
    "SISTEMA_DETENIDO": [("supervisor", "pid"), ("selector", "pid")],
    "LAZO_SIN_PARAMETROS": [("supervisor", "pid")],
    "RESISTENCIA_SIN_EFECTO": [("pid", "rele_ssr"), ("termomagnetica", "rele_ssr"), ("rele_ssr", "resistencia"),
                               ("resistencia", "tanque_principal"), ("bomba", "tanque_enfriador")],
    "CALENTANDO_A_SETPOINT": [("pid", "rele_ssr"), ("rele_ssr", "resistencia"), ("resistencia", "tanque_principal")],
    "EN_SETPOINT": [("pid", "rele_ssr"), ("resistencia", "tanque_principal"), ("sensor_principal", "tanque_principal")],
    "SOBRE_SETPOINT": [("plc", "enfriador"), ("enfriador", "tanque_enfriador"), ("tanque_enfriador", "tanque_principal")],
    "FUERA_DE_SETPOINT": [("pid", "rele_ssr"), ("bomba", "tanque_enfriador")],
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
    """Knowledge graph del modulo de temperatura: tanques, resistencia, rele de estado solido, bomba, variador,
    sensores Pt100, enfriador, interruptores de nivel, PID, PLC, selector y supervisor con sus variables UNS y
    relaciones (calienta, enfria, recircula, mide, controla...). Sin 'entidad' devuelve el grafo completo; con
    'entidad' (p. ej. 'tanque_principal', 'rele_ssr') sus relaciones y lo que influye aguas arriba."""
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
        ("obtener_lectura", lambda: obtener_lectura(["temperatura/principal_c", "estado/sistema_funcionando"])),
        ("consultar_historial", lambda: consultar_historial("temperatura/principal_c", minutos=120, puntos_max=10)),
        ("consultar_historial lvm 2010-07-24", lambda: consultar_historial("temperatura/principal_c",
                                                                         inicio="2010-07-24T10:38", fin="2010-07-24T14:35",
                                                                         puntos_max=10, fuente="lvm")),
        ("comparar_con_rango", lambda: comparar_con_rango()),
        ("diagnosticar_temperatura", lambda: diagnosticar_temperatura()),
        ("consultar_grafo rele_ssr", lambda: consultar_grafo("rele_ssr")),
    ]
    for nombre, f in pruebas:
        print(f"\n===== {nombre} =====")
        try:
            print(json.dumps(f(), ensure_ascii=False, indent=2, default=str)[:2500])
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor MCP solo lectura del modulo de temperatura MCT-09")
    ap.add_argument("--probar", action="store_true", help="ejecuta todas las herramientas una vez y termina")
    if ap.parse_args().probar:
        _probar()
    else:
        mcp.run()
