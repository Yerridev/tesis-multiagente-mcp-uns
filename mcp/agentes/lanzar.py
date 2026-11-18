#!/usr/bin/env python3
"""
Levanta el sistema multiagente completo (cada pieza es un proceso independiente):
  4 servidores MCP (uno por módulo) · 4 agentes analistas · 1 orquestador
Ctrl+C detiene todo. Los registros quedan en logs/agentes-*.log
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LOGS = RAIZ / "logs"
sys.path.insert(0, str(RAIZ / "mcp"))
from modulos import MODULOS  # noqa: E402

PY = sys.executable
PIDS = LOGS / "agentes.pids"


def detener_anterior():
    """Si quedó otra instancia abierta (otra ventana del bat 31), la detiene para liberar los puertos 8001-8004."""
    if not PIDS.exists():
        return
    pids = [p for p in PIDS.read_text().split() if p.isdigit()]
    if pids:
        print(f"Deteniendo la instancia anterior ({len(pids)} procesos)...", flush=True)
        for pid in pids:
            if sys.platform.startswith("win"):
                subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
            else:
                subprocess.run(["kill", "-9", pid], capture_output=True)
        time.sleep(2)
    PIDS.unlink(missing_ok=True)


def main():
    LOGS.mkdir(exist_ok=True)
    detener_anterior()
    procs = []

    def iniciar(nombre, args):
        log = open(LOGS / f"agentes-{nombre}.log", "a", encoding="utf-8")
        p = subprocess.Popen([PY, "-u", *args], cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT)
        procs.append((nombre, p))
        with open(PIDS, "a") as f:
            f.write(f"{p.pid}\n")
        print(f"  [OK] {nombre:<22} pid {p.pid}  → logs/agentes-{nombre}.log", flush=True)

    print("1) Servidores MCP (solo lectura):")
    for m, c in MODULOS.items():
        iniciar(f"mcp-{m}", ["mcp/server_modulo.py", "--modulo", m])
    time.sleep(4)
    print("2) Agentes analistas (uno por módulo):")
    for m in MODULOS:
        iniciar(f"analista-{m}", ["mcp/agentes/agente_modulo.py", "--modulo", m])
    print("3) Orquestador (intérprete + veredicto):")
    iniciar("orquestador", ["mcp/agentes/orquestador.py", "--servicio"])
    print("\nSistema multiagente en marcha. Deja esta ventana abierta; Ctrl+C para detener.")
    try:
        while True:
            time.sleep(5)
            for n, p in procs:
                if p.poll() is not None:
                    print(f"  [!] {n} se detuvo (código {p.returncode}); revisa logs/agentes-{n}.log", flush=True)
                    procs.remove((n, p))
                    break
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        for _, p in procs:
            p.terminate()
        PIDS.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
