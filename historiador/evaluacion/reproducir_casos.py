"""
Evaluacion reproducible de los diagnosticos de los servidores MCP sobre momentos reales guardados en el historiador.
Uso: EVALUAR_CASOS.bat  (o: python evaluacion/reproducir_casos.py) -> logs/evaluacion_casos.json y .md

La respuesta esperada de cada caso se fijo con lo que ocurrio fisicamente (cronograma del operador y notas de
campo), no con la salida de la herramienta:
  - caudal:      logs del conector y notas del 19-oct-2026 (diagnosticar_lazo)
  - presion:     pruebas del 21-oct-2026 (lazo abierto: Altivar en mando local) y del 24-oct-2026 (lazo cerrado,
                 escalones de setpoint 5 -> 10 -> 20 psi y prueba manual) (diagnosticar_presion)
  - temperatura: puesta en marcha del 23-oct-2026 (diagnosticar_temperatura)
Formato del esperado: "PRINCIPAL" o "PRINCIPAL + HALLAZGO_SECUNDARIO + ..." (los secundarios listados deben estar).
Los casos de NO_PUNTUADOS se reportan pero no cuentan en el puntaje (verdad de campo ambigua).
"""
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "mcp_servidor"))

# DSN del rol de solo lectura a partir del .env
cfg = {}
for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in linea and not linea.lstrip().startswith("#"):
        k, v = linea.split("=", 1)
        cfg[k.strip()] = v.strip()
os.environ.setdefault("MCP_DSN", f"postgresql://mcp_lector:{cfg.get('MCP_READER_PASSWORD', '')}@localhost:5432/"
                                 f"{cfg.get('DB_NAME', 'uns')}")
import servidor_mcp as s_caudal  # noqa: E402
import servidor_mcp_presion as s_presion  # noqa: E402
import servidor_mcp_temperatura as s_temperatura  # noqa: E402

DIAGNOSTICO = {
    "caudal": s_caudal.diagnosticar_lazo,
    "presion": s_presion.diagnosticar_presion,
    "temperatura": s_temperatura.diagnosticar_temperatura,
}

CASOS = [
    # --- Caudal MCC-09 (19-oct-2026) ---
    ("caudal", "C1", "2026-10-19T14:52:35", "Arranque: caudal subiendo de 4 a 25 L/min", "TRANSITORIO"),
    ("caudal", "C2", "2026-10-19T14:53:55", "1a prueba setpoint 60: variador 100 %, caudal ~58", "SATURADO_FUERA_DE_CAPACIDAD"),
    ("caudal", "C3", "2026-10-19T14:54:50", "Tras la 1a parada en saturacion", "BOMBA_DETENIDA + PARADA_TRAS_SATURACION"),
    ("caudal", "C4", "2026-10-19T14:56:40", "Regulacion estable a 40 L/min", "REGULANDO"),
    ("caudal", "C5", "2026-10-19T15:02:00", "Bomba detenida con setpoint 40 y PID al 100 %", "BOMBA_DETENIDA + INTEGRADOR_CARGADO"),
    ("caudal", "C6", "2026-10-19T15:05:00", "Regulacion estable a 11,5 L/min", "REGULANDO"),
    ("caudal", "C7", "2026-10-19T15:06:25", "Subida de setpoint 11,5 -> 40 (transitorio)", "TRANSITORIO"),
    ("caudal", "C8", "2026-10-19T15:12:00", "Regulacion estable a 40 L/min", "REGULANDO"),
    ("caudal", "C9", "2026-10-19T15:17:00", "2a prueba setpoint 60: variador 100 %, caudal ~57", "SATURADO_FUERA_DE_CAPACIDAD"),
    ("caudal", "C10", "2026-10-19T15:19:30", "Tras la 2a parada en saturacion", "BOMBA_DETENIDA + PARADA_TRAS_SATURACION"),
    ("caudal", "C11", "2026-10-19T15:31:00", "Selector en LOCAL con nivel bajo", "CONTROL_MANUAL_LOCAL + NIVEL_BAJO"),
    # --- Presion MCP-09: lazo abierto (21-oct-2026, Altivar en mando local de fabrica) ---
    ("presion", "P1", "2026-10-21T18:30:30", "LOCAL en marcha (velocidad por la perilla frontal del Altivar)", "MANUAL_EN_MARCHA"),
    ("presion", "P2", "2026-10-21T18:55:00", "REMOTO SP 20 psi: PID saturado a 10 V, presion ~0,1 psi (variador ignora AI1)", "ACTUADOR_NO_RESPONDE"),
    ("presion", "P3", "2026-10-21T19:22:30", "REMOTO SP 15 psi: PID saturado 6 min, presion ~0,7 psi", "ACTUADOR_NO_RESPONDE"),
    # --- Presion MCP-09: lazo cerrado (24-oct-2026, Altivar 2C/tEr/10U e Input 3 del AIO-610 en voltios) ---
    ("presion", "P4", "2026-10-24T18:29:50", "LOCAL con la perilla CONTROL MANUAL del tablero subiendo la presion", "MANUAL_EN_MARCHA"),
    ("presion", "P5", "2026-10-24T18:44:48", "Arranque REMOTO SP 5 psi: sobrepaso a 12,5 psi (PID saturado al arrancar)", "SOBRE_SETPOINT"),
    ("presion", "P6", "2026-10-24T18:46:30", "Regulacion estable: 5,43 psi con SP 5", "EN_SETPOINT"),
    ("presion", "P7", "2026-10-24T18:47:36", "Escalon SP 5 -> 10 psi (subida)", "SUBIENDO_A_SETPOINT"),
    ("presion", "P8", "2026-10-24T18:49:00", "Regulacion estable: 10,95 psi con SP 10", "EN_SETPOINT"),
    ("presion", "P9", "2026-10-24T18:50:27", "Escalon SP 10 -> 20 psi (subida)", "SUBIENDO_A_SETPOINT"),
    ("presion", "P10", "2026-10-24T18:53:30", "Sistema detenido tras bajar el SP a 2 psi y parar", "SISTEMA_DETENIDO"),
    # --- Temperatura MCT-09 (23-oct-2026) ---
    ("temperatura", "T1", "2026-10-23T22:18:30", "Lazo en marcha (modo PC) con setpoint 0: el PLC perdio los parametros", "LAZO_SIN_PARAMETROS"),
    ("temperatura", "T2", "2026-10-23T22:26:00", "Lazo detenido en modo PC tras el cambio LSr=tEr del Altivar", "SISTEMA_DETENIDO"),
]

# Verdad de campo ambigua: se reportan, no se puntuan
NO_PUNTUADOS = {
    "P11": ("presion", "2026-10-24T18:51:45",
            "Regulacion a 22,0 psi con SP 20: el PID regula en una escala ~10 % distinta de la HMI (EN_SETPOINT para el "
            "PID, SOBRE_SETPOINT para la escala de la HMI)"),
}


def evaluar(esperado: str, r: dict) -> bool:
    partes = [p.strip() for p in esperado.split("+")]
    if r["diagnostico"] != partes[0]:
        return False
    secundarios = {h["hallazgo"] for h in r.get("hallazgos_secundarios", [])}
    return all(p in secundarios for p in partes[1:])


def ejecutar(equipo: str, momento: str) -> tuple[dict, int]:
    t0 = time.perf_counter()
    r = DIAGNOSTICO[equipo](momento)
    return r, round((time.perf_counter() - t0) * 1000)


def obtenido_de(r: dict) -> str:
    return r["diagnostico"] + "".join(f" + {h['hallazgo']}" for h in r.get("hallazgos_secundarios", []))


resultados = []
for equipo, cid, momento, descripcion, esperado in CASOS:
    try:
        r, ms = ejecutar(equipo, momento)
        resultados.append({"equipo": equipo, "caso": cid, "momento": momento, "descripcion": descripcion,
                           "esperado": esperado, "obtenido": obtenido_de(r), "correcto": evaluar(esperado, r),
                           "latencia_ms": ms, "respuesta": r})
    except Exception as e:  # noqa: BLE001
        resultados.append({"equipo": equipo, "caso": cid, "momento": momento, "descripcion": descripcion,
                           "esperado": esperado, "obtenido": f"ERROR: {e}", "correcto": False, "latencia_ms": None})
    x = resultados[-1]
    print(f"{equipo:11} {cid:4} {momento}  {'OK ' if x['correcto'] else 'NO '} "
          f"esperado={esperado:40} obtenido={x['obtenido']}")

no_puntuados = []
for cid, (equipo, momento, descripcion) in NO_PUNTUADOS.items():
    try:
        r, ms = ejecutar(equipo, momento)
        no_puntuados.append({"equipo": equipo, "caso": cid, "momento": momento, "descripcion": descripcion,
                             "obtenido": obtenido_de(r), "latencia_ms": ms})
    except Exception as e:  # noqa: BLE001
        no_puntuados.append({"equipo": equipo, "caso": cid, "momento": momento, "descripcion": descripcion,
                             "obtenido": f"ERROR: {e}", "latencia_ms": None})

logs = RAIZ / "logs"
logs.mkdir(exist_ok=True)
(logs / "evaluacion_casos.json").write_text(
    json.dumps({"casos": resultados, "no_puntuados": no_puntuados}, ensure_ascii=False, indent=2, default=str),
    encoding="utf-8")

por_equipo = defaultdict(lambda: [0, 0])
for x in resultados:
    por_equipo[x["equipo"]][0] += x["correcto"]
    por_equipo[x["equipo"]][1] += 1
aciertos = sum(x["correcto"] for x in resultados)
latencias = sorted(x["latencia_ms"] for x in resultados if x["latencia_ms"] is not None)
mediana = latencias[len(latencias) // 2] if latencias else None

md = ["# Evaluacion de los diagnosticos MCP (reproduccion de datos reales)", "",
      f"**Aciertos totales: {aciertos}/{len(resultados)}** · latencia mediana {mediana} ms", "",
      "| Equipo | Aciertos |", "|---|---|"]
md += [f"| {eq} | {a}/{n} |" for eq, (a, n) in por_equipo.items()]
md += ["", "| Equipo | Caso | Momento | Situacion | Esperado | Obtenido | Correcto | Latencia (ms) |",
       "|---|---|---|---|---|---|---|---|"]
for x in resultados:
    md.append(f"| {x['equipo']} | {x['caso']} | {x['momento'].replace('T', ' ')} | {x['descripcion']} | {x['esperado']} | "
              f"{x['obtenido']} | {'si' if x['correcto'] else 'no'} | {x['latencia_ms']} |")
if no_puntuados:
    md += ["", "## Casos no puntuados (verdad de campo ambigua)", "",
           "| Equipo | Caso | Momento | Situacion | Obtenido |", "|---|---|---|---|---|"]
    md += [f"| {x['equipo']} | {x['caso']} | {x['momento'].replace('T', ' ')} | {x['descripcion']} | {x['obtenido']} |"
           for x in no_puntuados]
(logs / "evaluacion_casos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(f"\nAciertos: {aciertos}/{len(resultados)} ("
      + ", ".join(f"{eq} {a}/{n}" for eq, (a, n) in por_equipo.items()) + ")  ->  logs\\evaluacion_casos.md")
