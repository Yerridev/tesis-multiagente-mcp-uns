"""Simulador del modulo de presion MCP-09: cFP-2200 virtual (variables compartidas, puerto 6341) + tanque.

Uso:
    python -m simulador.presion --escenario simulador/escenarios/presion_fallas.json --acelerar 5

Conectores reales contra el simulador (sin cambiar su codigo, con el shim de DataSocket):
    Windows:  set PYTHONPATH=%CD%\\simulador\\psp_shim
              python conectores\\conector_edge_cfp2200.py --cfp 127.0.0.1 --broker 127.0.0.1
"""
from __future__ import annotations

import argparse
import asyncio

from .escenarios import cargar
from .motor import argumentos_comunes, bucle, con_llaves
from .llaves import LlavesPresion
from .plantas.presion import PlantaPresion
from .plcs.cfp2200_presion import CFP2200Presion
from .plcs.psp_sim import ServidorPSP

ENTRADAS = {"selector", "potenciometro_v", "arranque", "parada_ok", "nivel_alto_t1"}
ACCIONES = ENTRADAS | {"agua_t1", "sensor_congelado", "fuga", "plc_desconectado", "escribir"}


def aplicar(ev, plc: CFP2200Presion, srv: ServidorPSP):
    a, v = ev["accion"], ev.get("valor")
    if a in ENTRADAS:
        setattr(plc.ent, a, v)
    elif a == "agua_t1":
        plc.planta.e.agua_t1 = bool(v)
    elif a == "sensor_congelado":
        plc.planta.e.sensor_congelado = bool(v)
    elif a == "fuga":
        plc.planta.e.fuga = float(v)
    elif a == "plc_desconectado":
        asyncio.get_running_loop().create_task(srv.desconectar(bool(v)))
    elif a == "escribir":                       # {"url": "pid/setpoint_pc", "valor": 20}
        plc.vars[ev["url"]] = v


async def ejecutar(a):
    plc = CFP2200Presion(PlantaPresion(semilla=a.semilla))
    srv = ServidorPSP(plc, a.host, a.port)
    await srv.iniciar()
    escenario = cargar(a.escenario, ACCIONES) if a.escenario else None
    print(f"cFP-2200 virtual (presion) en {a.host}:{a.port}  |  aceleracion x{a.acelerar}"
          + (f"  |  escenario: {escenario.get('nombre')}" if escenario else ""))
    vplc, llaves = con_llaves(plc, LlavesPresion, a)   # llaves manuales + niveles (planta simulada)
    def aplicar_ev(ev):
        if llaves and ev['accion'] == 'agua_t1':   # el escenario vacia/llena T1 a traves de las llaves
            llaves.forzar('t1', 50.0 if ev.get('valor') else 5.0)
        else:
            aplicar(ev, plc, srv)
    await bucle(vplc, aplicar_ev, escenario, a.acelerar, a.log,
                lambda: "OK" if srv.conectado else "CAIDO")


def main():
    ap = argparse.ArgumentParser(description="Simulador del modulo de presion (cFP-2200 virtual)")
    argumentos_comunes(ap, 6341)
    try:
        asyncio.run(ejecutar(ap.parse_args()))
    except KeyboardInterrupt:
        print("\nSimulador detenido")


if __name__ == "__main__":
    main()
