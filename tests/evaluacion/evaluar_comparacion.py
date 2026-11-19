#!/usr/bin/env python3
"""
EXPERIMENTO COMPARATIVO — configuraciones A, B y C con la MISMA batería, modelo y herramientas MCP.

  A  Agente único con las 28 herramientas (línea base)
  B  Orquestador LLM (intérprete + veredicto) + 4 analistas por módulo   ← arquitectura propuesta
  C  Enrutador por reglas (sin IA) + 4 analistas + veredicto LLM

Ejecuta evaluar.py --config X para cada una (alternando el orden no hace falta: misma planta simulada
en operación normal) y deja un resumen comparativo en 05 ...\\Evidencias\\<fecha>-comparacion-ABC.md

Uso:  python tests/evaluacion/evaluar_comparacion.py --n 30 [--configs A,B,C]
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics as st
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "mcp" / "agentes"))
from comun import LIMA  # noqa: E402

NOMBRES = {"A": "Agente único (línea base)", "B": "Orquestador LLM + 4 analistas (propuesta)",
           "C": "Enrutador por reglas + 4 analistas"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--configs", default="A,B,C")
    a = ap.parse_args()
    base05 = next(RAIZ.parents[1].glob("05 - Evaluar*"))
    filas = []
    for c in [x.strip().upper() for x in a.configs.split(",") if x.strip()]:
        esc = f"simulada-config-{c}"
        print(f"\n================ CONFIGURACIÓN {c}: {NOMBRES[c]} ================", flush=True)
        r = subprocess.run([sys.executable, "-u", str(RAIZ / "tests" / "evaluacion" / "evaluar.py"),
                            "--n", str(a.n), "--escenario", esc, "--config", c], cwd=RAIZ)
        if r.returncode != 0:
            filas.append({"c": c, "error": f"terminó con código {r.returncode}"}); continue
        carpeta = sorted((base05 / "Evidencias").glob(f"*-{esc}"))[-1]
        with open(carpeta / "ejecutados.csv", encoding="utf-8-sig") as f:
            ej = list(csv.DictReader(f, delimiter=";"))
        t = [int(x["ms_total"]) / 1000 for x in ej]
        md = (carpeta / "indicadores.md").read_text(encoding="utf-8")
        traz = re.search(r"Índice de trazabilidad \| E_r / E_t × 100 \| \*\*([\d.]+) %\*\* \((\d+)/(\d+)", md)
        proc = re.search(r"\*\*(\d+) ms\*\* por llamada \(n = (\d+)\)", md)
        filas.append({
            "c": c, "carpeta": carpeta.name, "n": len(ej),
            "ok": sum(x["correcta"] == "True" for x in ej),
            "ruteo": sum(x["ok_ruteo"] == "True" for x in ej),
            "t": st.mean(t), "de": st.pstdev(t), "med": st.median(t),
            "err": sum(int(x["errores_consistencia"]) for x in ej),
            "mcp": st.mean(int(x["herramientas_mcp"]) for x in ej),
            "proc": proc.group(1) if proc else "—",
            "traz": f"{traz.group(1)} % ({traz.group(2)}/{traz.group(3)})" if traz else "—",
        })
    lin = [f"# Experimento comparativo A · B · C — planta simulada, operación normal ({datetime.now(LIMA):%Y-%m-%d %H:%M}, hora Lima)", "",
           "Constantes: batería de 10 preguntas, mismo modelo de lenguaje, mismos 4 servidores MCP (28 herramientas), misma planta.",
           "Variable manipulada: la forma de organizar los agentes.", "",
           "| Config. | Organización | Correctas | Ruteo correcto | Tiempo medio (s) | DE (s) | Mediana (s) | Llamadas MCP por consulta | Tiempo por llamada MCP (ms) | Errores de consistencia | Trazabilidad | Evidencia |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        if "error" in f:
            lin.append(f"| {f['c']} | {NOMBRES[f['c']]} | {f['error']} | | | | | | | | | |"); continue
        lin.append(f"| {f['c']} | {NOMBRES[f['c']]} | {f['ok']}/{f['n']} | {f['ruteo']}/{f['n']} | {f['t']:.2f} | {f['de']:.2f} | {f['med']:.2f} | "
                   f"{f['mcp']:.1f} | {f['proc']} | {f['err']} | {f['traz']} | [[Evidencias/{f['carpeta']}/indicadores|{f['carpeta']}]] |")
    lin += ["", "En A, «ruteo» = el agente usó herramientas de todos los módulos esperados; la consistencia se revisa sobre su respuesta única."]
    salida = base05 / "Evidencias" / f"{datetime.now(LIMA):%Y%m%d-%H%M}-comparacion-ABC.md"
    salida.write_text("\n".join(lin) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lin))
    print(f"\nResumen guardado en: {salida}")


if __name__ == "__main__":
    main()
