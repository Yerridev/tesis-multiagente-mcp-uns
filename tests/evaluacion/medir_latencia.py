#!/usr/bin/env python3
"""
Latencia PLC → backend (indicador VD-03, tiempo de procesamiento de datos).

Para cada dato: latencia = hora de LLEGADA al backend − hora en que el conector OBTUVO el dato del PLC
(campo "timestamp" del mensaje MQTT, con milisegundos). El backend lo calcula al recibir cada mensaje
(/api/latencia); este script reinicia el contador, espera, y guarda la evidencia en la carpeta 05.

Uso:  python tests/evaluacion/medir_latencia.py --segundos 120 --escenario simulada
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
LIMA = timezone(timedelta(hours=-5))


def token() -> str:
    if os.environ.get("SERVICIO_TOKEN"):
        return os.environ["SERVICIO_TOKEN"]
    try:
        for l in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
            if l.startswith("SERVICIO_TOKEN="):
                return l.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segundos", type=int, default=120)
    ap.add_argument("--escenario", default="simulada")
    ap.add_argument("--api", default=os.environ.get("BACKEND_URL", "http://127.0.0.1:8080"))
    a = ap.parse_args()
    cab = {"Authorization": f"Bearer {token()}"} if token() else {}
    api = a.api.rstrip("/")

    print(f"Reiniciando el medidor del backend ({api})...")
    r = httpx.post(f"{api}/api/latencia/reiniciar", headers=cab, timeout=10)
    r.raise_for_status()
    for s in range(a.segundos, 0, -10):
        print(f"  midiendo... faltan {s} s", flush=True)
        time.sleep(min(10, s))
    d = httpx.get(f"{api}/api/latencia?muestras=true", headers=cab, timeout=20).json()

    base05 = next(RAIZ.parents[1].glob("05 - Evaluar*"), RAIZ / "evidencias")
    salida = base05 / "Evidencias" / f"{datetime.now(LIMA):%Y%m%d-%H%M}-latencia-{a.escenario}"
    salida.mkdir(parents=True, exist_ok=True)

    with open(salida / "latencia.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["modulo", "senal", "recibido", "latencia_ms"])
        for m, info in sorted(d["modulos"].items()):
            for x in info.get("muestras") or []:
                w.writerow([m, x["senal"], x["recibido"], str(x["ms"]).replace(".", ",")])

    filas, todas = [], []
    for m in ("nivel", "caudal", "presion", "temperatura"):
        info = d["modulos"].get(m)
        if not info or not info["n"]:
            filas.append(f"| {m} | 0 | — | — | — | — | — |")
            continue
        todas += [x["ms"] for x in info["muestras"]]
        ok = "" if info["n"] >= 30 else " ⚠ n<30"
        filas.append(f"| {m} | {info['n']}{ok} | {info['mediaMs']:.1f} | {info['deMs']:.1f} | {info['medianaMs']:.1f} | {info['p95Ms']:.1f} | {info['descartadas']} |")
    media = sum(todas) / len(todas) if todas else 0
    md = [
        f"# Latencia PLC → backend — escenario `{a.escenario}`", "",
        f"- Ventana: {d['desde']} → {d['hasta']} ({a.segundos} s)",
        "- Latencia = llegada al backend − hora en que el conector obtuvo el dato del PLC (mismo reloj, ms)",
        "- Descartadas: mensajes retenidos/viejos (> 60 s), no son lecturas nuevas", "",
        "| Módulo | n | Media (ms) | DE (ms) | Mediana (ms) | p95 (ms) | Descartadas |",
        "|---|---|---|---|---|---|---|", *filas, "",
        f"**Promedio general:** {media:.1f} ms = {media / 1000:.3f} s (n = {len(todas)})",
        "", "Detalle por dato: `latencia.csv`",
    ]
    (salida / "latencia.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nEvidencia guardada en: {salida}")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as ex:
        print(f"ERROR: el backend no respondió ({ex}). ¿Está levantado Docker y reconstruido con el bat 05?")
        sys.exit(1)
