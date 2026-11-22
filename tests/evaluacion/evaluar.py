#!/usr/bin/env python3
"""
EVALUADOR del sistema multiagente MCP — mide los indicadores de la operacionalización (VI y VD).

Procedimiento (repetible):
  1. Toma una batería de preguntas con su RESPUESTA ESPERADA (qué módulos deben analizarse).
  2. Corre n preguntas (por defecto 30) contra el orquestador real (bat 31 corriendo).
  3. Antes y después de cada ejecución lee la VERDAD del backend (valores de los 4 PLC).
  4. Compara: ruteo del intérprete, que respondan todos los analistas, que los valores citados
     por cada analista coincidan con el backend (± tolerancia) y que haya veredicto.
  5. Lee las trazas (registros/agentes) y calcula el índice de trazabilidad.
  6. Deja la EVIDENCIA en la carpeta 05: ejecutados.csv, respuestas.json, trazas.jsonl, indicadores.md.

Uso:  python tests/evaluacion/evaluar.py --n 30 --escenario normal
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "mcp" / "agentes"))
from comun import LIMA, MODULOS, cfg  # noqa: E402
from orquestador import Orquestador  # noqa: E402
from agente_unico import AgenteUnico  # noqa: E402

# Configuraciones del experimento (misma batería, mismo modelo, mismas herramientas MCP)
CONFIGS = {
    "A": "Agente único con las 28 herramientas MCP (línea base)",
    "B": "Orquestador LLM (intérprete + veredicto) + 4 analistas por módulo",
    "C": "Enrutador por reglas (sin IA) + 4 analistas + veredicto LLM",
}
AGENTES = {"A": 1, "B": 5, "C": 5}

BACKEND = cfg("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
CAB = {"Authorization": f"Bearer {cfg('SERVICIO_TOKEN')}"} if cfg("SERVICIO_TOKEN") else {}
TOL = {"nivel": 1.5, "caudal": 3.0, "presion": 1.0, "temperatura": 1.0}   # tolerancia de consistencia (unidades del módulo)
TODOS = list(MODULOS)

BATERIA = [
    ("Q01", "¿Cómo está la planta ahora?", TODOS, "estado general"),
    ("Q02", "¿Cuál es el caudal actual y está cerca de su setpoint?", ["caudal"], "consulta de valor"),
    ("Q03", "¿La temperatura del tanque principal llega a su setpoint?", ["temperatura"], "consulta de valor"),
    ("Q04", "¿Qué nivel tiene el tanque T2 del módulo de nivel?", ["nivel"], "consulta de valor"),
    ("Q05", "¿Cuál es la presión del tanque T2 y en qué modo está el selector?", ["presion"], "consulta de estado"),
    ("Q06", "¿Hay alguna alarma activa en la planta?", TODOS, "diagnóstico"),
    ("Q07", "¿El módulo de caudal está en LOCAL o en REMOTO?", ["caudal"], "consulta de estado"),
    ("Q08", "Compara la presión y el caudal: ¿ambos están estables?", ["presion", "caudal"], "integración de módulos"),
    ("Q09", "¿El sensor de nivel está funcionando bien?", ["nivel"], "diagnóstico"),
    ("Q10", "¿Qué módulos están en marcha ahora?", TODOS, "estado general"),
]


def verdad() -> dict:
    """Valor principal de cada módulo según el backend (la referencia)."""
    try:
        eqs = httpx.get(f"{BACKEND}/api/equipment", headers=CAB, timeout=10).json()
    except Exception:  # noqa: BLE001
        return {}
    por_id = {e.get("id"): e for e in eqs}
    return {m: {"valor": (por_id.get(c["equipo"]) or {}).get("value"),
                "estado": (por_id.get(c["equipo"]) or {}).get("status")} for m, c in MODULOS.items()}


NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
# La respuesta final MENCIONA la falla de comunicación (criterio común a A, B y C)
FALLA_TXT = re.compile(r"sin comunicaci|desconect|offline|fuera de l[ií]nea|no responde|sin conexi|sin datos|no hay datos|"
                       r"desactualiz|no est[aá] (?:disponible|en l[ií]nea)|ca[ií]d|p[eé]rdida de comunicaci|sin telemetr|no fresc|obsolet", re.I)


def consistencia(texto: str, refs: list) -> str:
    """'ok' si el texto cita un número cercano a la verdad; 'error' si cita números y ninguno coincide; 'na' si no cita."""
    vals = [(v, t) for v, t in refs if isinstance(v, (int, float))]
    if not vals:
        return "na"
    nums = [float(n.replace(",", ".")) for n in NUM.findall(texto or "")]
    return "na" if not nums else ("ok" if any(abs(n - v) <= tol for n in nums for v, tol in vals) else "error")


def evaluar_trazas(corrs: set[str]) -> tuple[list[dict], int, int]:
    """Índice de trazabilidad: eventos con corr, agente, ts y (si aplica) ms, sobre el total de eventos de esas ejecutados."""
    filas = []
    for f in sorted((RAIZ / "registros" / "agentes").glob("*.jsonl")):
        for linea in f.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if d.get("corr") in corrs:
                filas.append(d)
    def completo(d):
        base = all(d.get(k) for k in ("ts", "corr", "agente", "evento"))
        if d["evento"] in ("herramienta_mcp", "informe_modulo", "veredicto", "interpretacion"):
            base = base and isinstance(d.get("ms"), (int, float))
        if d["evento"] == "respuesta":
            base = base and isinstance(d.get("ms_total"), (int, float))
        return base
    return filas, sum(1 for d in filas if completo(d)), len(filas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--escenario", default="normal", help="etiqueta del escenario (normal, falla-caudal, ...)")
    ap.add_argument("--falla", default="", help="módulo con falla inyectada: el sistema DEBE reportarlo con severidad >= advertencia")
    ap.add_argument("--pausa", type=float, default=2.0)
    ap.add_argument("--config", default="B", choices=list(CONFIGS), help="A agente único · B orquestador LLM · C enrutador por reglas")
    a = ap.parse_args()

    base05 = next(RAIZ.parents[1].glob("05 - Evaluar*"), RAIZ / "evidencias")
    salida = base05 / "Evidencias" / f"{datetime.now(LIMA):%Y%m%d-%H%M}-{a.escenario}"
    salida.mkdir(parents=True, exist_ok=True)
    print(f"Evidencia → {salida}")

    o = AgenteUnico() if a.config == "A" else Orquestador()
    print(f"Configuración {a.config}: {CONFIGS[a.config]}")
    ejecutados, resultados = [], []
    for i in range(a.n):
        qid, pregunta, esperados, tipo = BATERIA[i % len(BATERIA)]
        v0 = verdad()
        r = o.preguntar(pregunta, origen=f"evaluacion-{a.escenario}", **({"enrutador_reglas": True} if a.config == "C" else {}))
        v1 = verdad()
        resultados.append(r)
        plan = list(r["plan"])
        ok_ruteo = set(esperados) <= set(plan)
        precision = len(set(esperados) & set(plan)) / len(plan) if plan else 0
        ok_respuesta = not r["sin_respuesta"] and len(r["informes"]) == len(plan)
        cons = {}
        for inf in r["informes"]:
            m = inf["modulo"]
            refs = [(x.get(m, {}).get("valor"), TOL[m]) for x in (v0, v1)]
            refs = [(v, t) for v, t in refs if isinstance(v, (int, float))]
            cons[m] = consistencia(inf.get("resumen", ""), refs)
        errores = sum(1 for c in cons.values() if c == "error")
        ok_veredicto = bool((r["veredicto"].get("respuesta") or "").strip())
        detecta, detecta_texto = "", ""
        if a.falla:
            consultado = a.falla in plan
            menciona = bool(FALLA_TXT.search(r["veredicto"].get("respuesta") or ""))
            detecta_texto = ("si" if menciona else "no") if consultado else "no_consultado"
            if a.config == "A":   # sin severidad determinista: cuenta si la respuesta menciona la falla
                detecta = detecta_texto
            else:
                inf_f = next((x for x in r["informes"] if x["modulo"] == a.falla), None)
                detecta = "si" if inf_f and inf_f.get("severidad") in ("advertencia", "alarma") else ("no" if inf_f else "no_consultado")
        correcta = ok_ruteo and ok_respuesta and errores == 0 and ok_veredicto and detecta in ("", "si", "no_consultado")
        fila = {
            "config": a.config, "n": i + 1, "id": qid, "tipo": tipo, "pregunta": pregunta, "corr": r["corr"],
            "esperados": "+".join(esperados), "plan": "+".join(plan), "interprete": r["interprete"],
            "ok_ruteo": ok_ruteo, "precision_ruteo": round(precision, 2),
            "analistas": len(plan), "respondieron": len(r["informes"]), "ok_respuesta": ok_respuesta,
            "consistencia": " ".join(f"{k}:{v}" for k, v in cons.items()), "errores_consistencia": errores,
            "herramientas_mcp": sum(len(x.get("herramientas", [])) for x in r["informes"]),
            "modo_analistas": "+".join(sorted({x.get("modo", "?") for x in r["informes"]})),
            "modo_veredicto": r["veredicto"].get("modo"), "modelo": r["veredicto"].get("modelo") or "",
            "severidad": r["veredicto"].get("severidad"), "detecta_falla": detecta, "detecta_texto": detecta_texto,
            "ms_total": r["ms_total"], "correcta": correcta,
        }
        ejecutados.append(fila)
        print(f"[{i + 1:>2}/{a.n}] {qid} {'OK ' if correcta else 'NO '} {r['ms_total']:>6} ms  plan={fila['plan']:<32} cons={fila['consistencia']}", flush=True)
        time.sleep(a.pausa)

    # ------------------------------------------------------------------ evidencia
    with open(salida / "ejecutados.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(ejecutados[0]), delimiter=";")
        w.writeheader()
        w.writerows(ejecutados)
    (salida / "respuestas.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    trazas, completas, total_ev = evaluar_trazas({c["corr"] for c in ejecutados})
    (salida / "trazas.jsonl").write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in trazas), encoding="utf-8")

    # ------------------------------------------------------------------ indicadores
    n = len(ejecutados)
    t = [c["ms_total"] / 1000 for c in ejecutados]
    ok = sum(c["correcta"] for c in ejecutados)
    tools_ms = [d["ms"] for d in trazas if d["evento"] == "herramienta_mcp" and isinstance(d.get("ms"), (int, float))]
    tools_ok = sum(1 for d in trazas if d["evento"] == "herramienta_mcp" and d.get("ok"))
    tools_tot = sum(1 for d in trazas if d["evento"] == "herramienta_mcp")
    v = verdad()
    activas = sum(1 for m in v.values() if m.get("estado") == "ONLINE")
    p95 = sorted(t)[max(0, int(round(0.95 * n)) - 1)]
    errores = sum(c["errores_consistencia"] for c in ejecutados)
    tipos = sorted({c["tipo"] for c in ejecutados})
    flujos = sum(1 for c in ejecutados if c["respondieron"] > 0)
    lin = [
        f"# Evaluación del sistema multiagente MCP — escenario `{a.escenario}`",
        "",
        f"- Fecha: {datetime.now(LIMA):%Y-%m-%d %H:%M} (hora Lima)",
        f"- Ejecutados: **n = {n}** · batería de {len(BATERIA)} preguntas · modelo: {ejecutados[-1]['modelo'] or 'reglas'}",
        f"- Planta: {'simulada' if 'sim' in a.escenario or a.escenario == 'normal' else a.escenario} · falla inyectada: {a.falla or 'ninguna'}",
        f"- Configuración: **{a.config}** — {CONFIGS[a.config]}",
        "- Evidencia: `ejecutados.csv` (una fila por ejecución), `respuestas.json` (respuestas completas), `trazas.jsonl` (eventos)",
        "",
        "## Variable independiente — Arquitectura multiagente basada en IA con MCP",
        "",
        "| Dimensión | Indicador | Fórmula / medición | Resultado |",
        "|---|---|---|---|",
        f"| Configuración | N.º de agentes configurados | conteo | **{AGENTES[a.config]}** ({CONFIGS[a.config]}) |",
        f"| Configuración | N.º de herramientas MCP | conteo | **{7 * len(MODULOS)}** (7 × {len(MODULOS)} servidores) |",
        f"| Configuración | N.º de fuentes de datos conectadas | conteo | **{len(MODULOS)}** PLC |",
        f"| Rendimiento | Tiempo promedio de respuesta | T = Σtᵢ / n | **{st.mean(t):.2f} s** (DE {st.pstdev(t):.2f} · mediana {st.median(t):.2f} · p95 {p95:.2f}) |",
        f"| Rendimiento | N.º de consultas procesadas correctamente | conteo | **{ok} de {n}** |",
        f"| Automatización | N.º de tareas automatizadas | conteo de tipos de tarea | **{len(tipos)}** ({', '.join(tipos)}) |",
        f"| Automatización | Tasa de éxito | T_ok / T_tot × 100 | **{100 * ok / n:.1f} %** |",
        "",
        "## Variable dependiente — Orquestación e integración de datos industriales",
        "",
        "| Dimensión | Indicador | Fórmula / medición | Resultado |",
        "|---|---|---|---|",
        f"| Eficiencia de integración | % de fuentes integradas | F_i / F_t × 100 | **{100 * len(MODULOS) / 4:.0f} %** ({len(MODULOS)}/4) |",
        f"| Eficiencia de integración | N.º de conexiones activas | conteo | **{activas}** PLC ONLINE + {len(MODULOS)} servidores MCP |",
        f"| Orquestación | Tiempo promedio de procesamiento (herramienta MCP) | T = Σtᵢ / n | **{st.mean(tools_ms):.0f} ms** por llamada (n = {len(tools_ms)}) |" if tools_ms else "| Orquestación | Tiempo de procesamiento | — | sin datos |",
        "| Orquestación | Reducción de tareas manuales | (M_pre − M_post) / M_pre × 100 | ver bitácora pre/post |",
        f"| Orquestación | N.º de flujos orquestados automáticamente | conteo | **{flujos}** |",
        f"| Calidad y trazabilidad | N.º de errores de consistencia | conteo | **{errores}** |",
        f"| Calidad y trazabilidad | Índice de trazabilidad | E_r / E_t × 100 | **{100 * completas / total_ev:.1f} %** ({completas}/{total_ev} eventos) |" if total_ev else "| Calidad | Índice de trazabilidad | — | sin trazas |",
        "",
        "## Detalle",
        "",
        f"- Ruteo del intérprete correcto: {sum(c['ok_ruteo'] for c in ejecutados)}/{n} · precisión media {st.mean(c['precision_ruteo'] for c in ejecutados):.2f}",
        f"- Todos los analistas respondieron: {sum(c['ok_respuesta'] for c in ejecutados)}/{n}",
        f"- Llamadas a herramientas MCP exitosas: {tools_ok}/{tools_tot}",
        f"- Analistas con IA + MCP: {sum('llm+mcp' in c['modo_analistas'] for c in ejecutados)}/{n} ejecutados",
    ]
    if a.falla:
        det = [c for c in ejecutados if c["detecta_falla"] in ("si", "no")]
        lin.append(f"- Falla en `{a.falla}` detectada: {sum(c['detecta_falla'] == 'si' for c in det)}/{len(det)} ejecutados que consultaron ese módulo")
        dt = [c for c in ejecutados if c["detecta_texto"] in ("si", "no")]
        lin.append(f"- Falla mencionada en la respuesta final: {sum(c['detecta_texto'] == 'si' for c in dt)}/{len(dt)} ejecutados que consultaron ese módulo")
    lin += ["", "### Por pregunta", "", "| ID | Tipo | Ejecutados | Correctas | Tiempo medio (s) |", "|---|---|---|---|---|"]
    for qid, _, _, tipo in BATERIA:
        cs = [c for c in ejecutados if c["id"] == qid]
        if cs:
            lin.append(f"| {qid} | {tipo} | {len(cs)} | {sum(c['correcta'] for c in cs)} | {st.mean(c['ms_total'] for c in cs) / 1000:.2f} |")
    lin += ["", "### Criterio de consulta correcta",
            "Ruteo correcto (el intérprete incluye los módulos esperados) **y** respondieron todos los analistas **y** "
            f"ningún analista citó un valor fuera de tolerancia respecto del backend ({', '.join(f'{k} ±{v}' for k, v in TOL.items())}) "
            "**y** hubo veredicto" + (" **y** el módulo con falla se reportó con severidad ≥ advertencia." if a.falla else ".")]
    (salida / "indicadores.md").write_text("\n".join(lin) + "\n", encoding="utf-8")
    print("\n".join(lin[8:30]))
    print(f"\nEvidencia guardada en: {salida}")


if __name__ == "__main__":
    main()
