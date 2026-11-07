"""Simulador del modulo de nivel MCN-09: MicroLogix 1100 virtual (EtherNet/IP-PCCC, puerto 44818) + tanque.

Uso:
    python -m simulador.nivel                                   # escucha en 127.0.0.1:44818
    python -m simulador.nivel --escenario simulador/escenarios/nivel_fallas.json --acelerar 5

Conectores reales contra el simulador:
    python conectores/conector_edge_ml1100.py --plc 127.0.0.1 --broker 127.0.0.1
"""
from __future__ import annotations

import argparse
import asyncio

from .escenarios import cargar
from .motor import argumentos_comunes, bucle
from .plantas.nivel import PlantaNivel
from .plcs.enip_pccc import ServidorENIP
from .plcs.micrologix_nivel import MicroLogixNivel

ENTRADAS = {"selector", "nivel_alto_t1", "paro_ok", "arranque", "potenciometro"}
ACCIONES = ENTRADAS | {"agua_t1", "sensor_congelado", "fuga_lpm", "plc_desconectado",
                       "escribir_n", "escribir_b"}


def aplicar(ev: dict, plc: MicroLogixNivel, srv: ServidorENIP):
    a, v = ev["accion"], ev.get("valor")
    if a in ENTRADAS:
        setattr(plc.ent, a, v)
    elif a == "agua_t1":
        plc.planta.e.agua_t1 = bool(v)
    elif a == "sensor_congelado":
        plc.planta.e.sensor_congelado = bool(v)
    elif a == "fuga_lpm":
        plc.planta.e.fuga_lpm = float(v)
    elif a == "plc_desconectado":
        asyncio.get_running_loop().create_task(srv.desconectar(bool(v)))
    elif a == "escribir_n":                      # {"direccion": 5, "valor": 8348} -> N7:5
        plc.t.poner(7, int(ev["direccion"]), int(v))
    elif a == "escribir_b":                      # {"bit": 4, "valor": true} -> B3:0/4
        plc.t.poner_bit(3, int(ev["bit"]), bool(v))


async def ejecutar(a):
    plc = MicroLogixNivel(PlantaNivel(semilla=a.semilla))
    srv = ServidorENIP(plc.t, a.host, a.port)
    await srv.iniciar()
    escenario = cargar(a.escenario, ACCIONES) if a.escenario else None
    print(f"MicroLogix 1100 virtual (nivel) en {a.host}:{a.port}  |  aceleracion x{a.acelerar}"
          + (f"  |  escenario: {escenario.get('nombre')}" if escenario else ""))
    await bucle(plc, lambda ev: aplicar(ev, plc, srv), escenario, a.acelerar, a.log,
                lambda: "OK" if srv.conectado else "CAIDO")


def main():
    ap = argparse.ArgumentParser(description="Simulador del modulo de nivel (MicroLogix 1100 virtual)")
    argumentos_comunes(ap, 44818)
    try:
        asyncio.run(ejecutar(ap.parse_args()))
    except KeyboardInterrupt:
        print("\nSimulador detenido")


if __name__ == "__main__":
    main()
