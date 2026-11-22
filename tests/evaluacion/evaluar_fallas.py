#!/usr/bin/env python3
"""
EVALUACIÓN CON FALLAS (planta SIMULADA) — un módulo a la vez.

Para cada módulo:
  1. Inyecta la falla en su PLC virtual por MQTT (<UNS>/<equipo>/sim/cmd/falla). Solo existe en el simulador.
  2. Espera a que el backend marque el módulo OFFLINE (confirma que la falla está activa).
  3. Ejecuta la batería (evaluar.py --falla <modulo>): el sistema DEBE reportar el módulo con severidad >= advertencia.
  4. Quita la falla y espera a que el módulo vuelva a ONLINE (siempre, aunque algo falle).
Al final deja un resumen en 05 ...\\Evidencias\\<fecha>-fallas-resumen.md

Uso:  python tests/evaluacion/evaluar_fallas.py --n 10 [--modulos nivel,caudal,presion,temperatura]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "mcp" / "agentes"))
from comun import LIMA, MODULOS, cfg  # noqa: E402

UNS = "uss/campus/lab-automatizacion/sl01la07"
BASE_SIM = {"nivel": "nivel-mcn09", "caudal": "caudal-mcc09", "presion": "presion-mcp09", "temperatura": "temperatura-mct09"}
BACKEND = cfg("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
CAB = {"Authorization": f"Bearer {cfg('SERVICIO_TOKEN')}"} if cfg("SERVICIO_TOKEN") else {}
FALLA = "plc_desconectado"


def estado(modulo: str) -> str | None:
    try:
        eqs = httpx.get(f"{BACKEND}/api/equipment", headers=CAB, timeout=10).json()
    except Exception:  # noqa: BLE001
        return None
    eq = next((e for e in eqs if e.get("id") == MODULOS[modulo]["equipo"]), None)
    return eq.get("status") if eq else None


def esperar(modulo: str, objetivo: str, limite: int) -> bool:
    for s in range(0, limite, 3):
        e = estado(modulo)
        print(f"    {modulo}: {e}  (esperado {objetivo}, {s} s)", flush=True)
        if e == objetivo:
            return True
        time.sleep(3)
    return False


def inyectar(cli: mqtt.Client, modulo: str, valor: bool):
    topico = f"{UNS}/{BASE_SIM[modulo]}/sim/cmd/falla"
    cli.publish(topico, json.dumps({"accion": FALLA, "valor": valor}), qos=1).wait_for_publish(5)
    print(f"  -> {'INYECTADA' if valor else 'QUITADA'}: {FALLA} en {modulo}  ({topico})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="ejecutados por módulo (10 = la batería una vez)")
    ap.add_argument("--modulos", default="nivel,caudal,presion,temperatura")
    ap.add_argument("--config", default="B", choices=["A", "B", "C"])
    ap.add_argument("--broker", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=1883)
    a = ap.parse_args()
    modulos = [m.strip() for m in a.modulos.split(",") if m.strip()]

    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="evaluador-fallas")
    cli.connect(a.broker, a.puerto, keepalive=30)
    cli.loop_start()

    py = sys.executable
    filas = []
    for m in modulos:
        print(f"\n================ FALLA EN {m.upper()} ================", flush=True)
        if estado(m) != "ONLINE":
            print(f"  {m} no está ONLINE antes de empezar: ¿planta simulada en marcha (bat 10)? Se omite.")
            filas.append((m, "omitido", "", "", "")); continue
        try:
            inyectar(cli, m, True)
            if not esperar(m, "OFFLINE", 60):
                print(f"  la falla no se reflejó en el backend: se omite {m}")
                filas.append((m, "falla no activa", "", "", "")); continue
            esc = f"simulada-falla-{m}" + ("" if a.config == "B" else f"-config-{a.config}")
            r = subprocess.run([py, "-u", str(RAIZ / "tests" / "evaluacion" / "evaluar.py"), "--n", str(a.n),
                                "--escenario", esc, "--falla", m, "--config", a.config], cwd=RAIZ)
            carpeta = sorted((next(RAIZ.parents[1].glob("05 - Evaluar*")) / "Evidencias").glob(f"*-{esc}"))[-1]
            md = (carpeta / "indicadores.md").read_text(encoding="utf-8")
            ok = re.search(r"consultas procesadas correctamente \| conteo \| \*\*(\d+) de (\d+)\*\*", md)
            det = re.search(r"Falla en `\w+` detectada: (\d+)/(\d+)", md)
            txt = re.search(r"Falla mencionada en la respuesta final: (\d+)/(\d+)", md)
            t = re.search(r"Tiempo promedio de respuesta \| T = Σtᵢ / n \| \*\*([\d.]+) s\*\*", md)
            filas.append((m, "ok" if r.returncode == 0 else f"error {r.returncode}",
                          f"{ok.group(1)}/{ok.group(2)}" if ok else "?", f"{det.group(1)}/{det.group(2)}" if det else "?",
                          t.group(1) if t else "?", carpeta.name, f"{txt.group(1)}/{txt.group(2)}" if txt else "?"))
        finally:
            inyectar(cli, m, False)
            esperar(m, "ONLINE", 90)

    cli.loop_stop()
    base05 = next(RAIZ.parents[1].glob("05 - Evaluar*"))
    lin = [f"# Evaluación con fallas — configuración {a.config} — planta simulada ({datetime.now(LIMA):%Y-%m-%d %H:%M}, hora Lima)", "",
           f"Falla inyectada: **{FALLA}** (el PLC virtual deja de responder), un módulo a la vez; {a.n} ejecutados por módulo.",
           "Correcta = criterio normal **y** el analista del módulo con falla lo reporta con severidad ≥ advertencia.", "",
           "| Módulo con falla | Correctas | Falla detectada (ejecutados que consultaron el módulo) | Falla mencionada en la respuesta | Tiempo medio (s) | Evidencia |",
           "|---|---|---|---|---|---|"]
    for f in filas:
        if len(f) == 7:
            lin.append(f"| {f[0]} | {f[2]} | {f[3]} | {f[6]} | {f[4]} | [[Evidencias/{f[5]}/indicadores|{f[5]}]] |")
        else:
            lin.append(f"| {f[0]} | {f[1]} | — | — | — | — |")
    salida = base05 / "Evidencias" / f"{datetime.now(LIMA):%Y%m%d-%H%M}-fallas-resumen-config-{a.config}.md"
    salida.write_text("\n".join(lin) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lin))
    print(f"\nResumen guardado en: {salida}")


if __name__ == "__main__":
    main()
