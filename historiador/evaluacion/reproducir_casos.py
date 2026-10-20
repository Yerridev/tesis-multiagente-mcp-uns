"""
Evaluacion reproducible del diagnostico (diagnosticar_lazo) sobre momentos reales guardados en el historiador.
Uso: EVALUAR_CASOS.bat  (o: python evaluacion/reproducir_casos.py) -> logs/evaluacion_casos.json y .md
Cada caso tiene la respuesta esperada, verificada con los logs del conector del 19-oct-2026.
"""
import json
import os
import sys
import time
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
import servidor_mcp as s  # noqa: E402

CASOS = [
    ("C1", "2026-10-19T14:52:35", "Arranque: caudal subiendo de 4 a 25 L/min", "TRANSITORIO"),
    ("C2", "2026-10-19T14:53:55", "1a prueba setpoint 60: variador 100 %, caudal ~58", "SATURADO_FUERA_DE_CAPACIDAD"),
    ("C3", "2026-10-19T14:54:50", "Tras la 1a parada en saturacion", "BOMBA_DETENIDA + PARADA_TRAS_SATURACION"),
    ("C4", "2026-10-19T14:56:40", "Regulacion estable a 40 L/min", "REGULANDO"),
    ("C5", "2026-10-19T15:02:00", "Bomba detenida con setpoint 40 y PID al 100 %", "BOMBA_DETENIDA + INTEGRADOR_CARGADO"),
    ("C6", "2026-10-19T15:05:00", "Regulacion estable a 11,5 L/min", "REGULANDO"),
    ("C7", "2026-10-19T15:06:25", "Subida de setpoint 11,5 -> 40 (transitorio)", "TRANSITORIO"),
    ("C8", "2026-10-19T15:12:00", "Regulacion estable a 40 L/min", "REGULANDO"),
    ("C9", "2026-10-19T15:17:00", "2a prueba setpoint 60: variador 100 %, caudal ~57", "SATURADO_FUERA_DE_CAPACIDAD"),
    ("C10", "2026-10-19T15:19:30", "Tras la 2a parada en saturacion", "BOMBA_DETENIDA + PARADA_TRAS_SATURACION"),
    ("C11", "2026-10-19T15:31:00", "Selector en LOCAL con nivel bajo", "CONTROL_MANUAL_LOCAL + NIVEL_BAJO"),
]


def evaluar(esperado: str, r: dict) -> bool:
    partes = [p.strip() for p in esperado.split("+")]
    if r["diagnostico"] != partes[0]:
        return False
    secundarios = {h["hallazgo"] for h in r["hallazgos_secundarios"]}
    return all(p in secundarios for p in partes[1:])


resultados = []
for cid, momento, descripcion, esperado in CASOS:
    t0 = time.perf_counter()
    try:
        r = s.diagnosticar_lazo(momento)
        ms = round((time.perf_counter() - t0) * 1000)
        obtenido = r["diagnostico"] + "".join(f" + {h['hallazgo']}" for h in r["hallazgos_secundarios"])
        ok = evaluar(esperado, r)
        resultados.append({"caso": cid, "momento": momento, "descripcion": descripcion, "esperado": esperado,
                           "obtenido": obtenido, "correcto": ok, "latencia_ms": ms, "respuesta": r})
    except Exception as e:  # noqa: BLE001
        resultados.append({"caso": cid, "momento": momento, "descripcion": descripcion, "esperado": esperado,
                           "obtenido": f"ERROR: {e}", "correcto": False, "latencia_ms": None})
    print(f"{cid:4} {momento[11:]}  {'OK ' if resultados[-1]['correcto'] else 'NO '} "
          f"esperado={esperado:42} obtenido={resultados[-1]['obtenido']}")

logs = RAIZ / "logs"
logs.mkdir(exist_ok=True)
(logs / "evaluacion_casos.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2, default=str),
                                            encoding="utf-8")
aciertos = sum(r["correcto"] for r in resultados)
md = ["# Evaluacion de diagnosticar_lazo (reproduccion de datos reales, 19-oct-2026)", "",
      f"Aciertos: {aciertos}/{len(resultados)}", "",
      "| Caso | Hora | Situacion | Esperado | Obtenido | Correcto | Latencia (ms) |", "|---|---|---|---|---|---|---|"]
for r in resultados:
    md.append(f"| {r['caso']} | {r['momento'][11:]} | {r['descripcion']} | {r['esperado']} | {r['obtenido']} | "
              f"{'si' if r['correcto'] else 'no'} | {r['latencia_ms']} |")
(logs / "evaluacion_casos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(f"\nAciertos: {aciertos}/{len(resultados)}  ->  logs\\evaluacion_casos.md")
