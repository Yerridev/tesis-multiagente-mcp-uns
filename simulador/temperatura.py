"""Simulador del modulo de temperatura MCT-09: PLC Twido virtual (Modbus TCP) + planta termica.

Uso (Windows, en la carpeta del proyecto):
    python -m simulador.temperatura                       # escucha en 127.0.0.1:502
    python -m simulador.temperatura --acelerar 10          # 10x mas rapido
    python -m simulador.temperatura --escenario simulador/escenarios/temperatura_fallas.json

Luego los conectores reales apuntan al simulador:
    python conectores/conector_edge_twido.py --plc 127.0.0.1 --broker 127.0.0.1
    python conectores/conector_control_temperatura.py --plc 127.0.0.1 --habilitado-real
"""
from __future__ import annotations

import argparse
import asyncio
from .escenarios import ACCIONES_ENTRADA, cargar
from .motor import argumentos_comunes, bucle, con_llaves
from .llaves import LlavesTemperatura
from .plantas.temperatura import ParametrosTemperatura, PlantaTemperatura
from .plcs.modbus_tcp import ServidorModbus
from .plcs.twido_temperatura import TwidoTemperatura

def aplicar(ev: dict, plc: TwidoTemperatura, srv: ServidorModbus):
    a, v = ev["accion"], ev.get("valor")
    if a in ACCIONES_ENTRADA:
        setattr(plc.ent, a, v)
    elif a == "sensor_congelado":
        plc.planta.e.sensor_congelado = bool(v)
    elif a == "t_ambiente":
        plc.planta.p.t_ambiente = float(v)
    elif a == "plc_desconectado":
        srv.desconectar(bool(v))
    elif a == "escribir_mw":
        plc.mem.regs[int(ev["direccion"])] = int(v)
    elif a == "escribir_m":
        plc.mem.coils[int(ev["direccion"])] = bool(v)


async def ejecutar(a):
    planta = PlantaTemperatura(ParametrosTemperatura(t_ambiente=a.t_ambiente), semilla=a.semilla)
    plc = TwidoTemperatura(planta)
    srv = ServidorModbus(plc.mem, a.host, a.port)
    await srv.iniciar()
    escenario = cargar(a.escenario) if a.escenario else None
    print(f"Twido virtual (temperatura) en {a.host}:{a.port}  |  aceleracion x{a.acelerar}"
          + (f"  |  escenario: {escenario.get('nombre')}" if escenario else ""))
    vplc, llaves = con_llaves(plc, LlavesTemperatura, a)   # llaves manuales + niveles (planta simulada)
    def aplicar_ev(ev):
        if llaves and ev['accion'] == 'agua_t1':   # el escenario vacia/llena T1 a traves de las llaves
            llaves.forzar('t1', 50.0 if ev.get('valor') else 5.0)
        else:
            aplicar(ev, plc, srv)
    await bucle(vplc, aplicar_ev, escenario, a.acelerar, a.log,
                lambda: "OK" if srv.conectado else "CAIDO")


def main():
    ap = argparse.ArgumentParser(description="Simulador del modulo de temperatura (Twido virtual)")
    argumentos_comunes(ap, 502)
    ap.add_argument("--t-ambiente", type=float, default=20.0)
    try:
        asyncio.run(ejecutar(ap.parse_args()))
    except KeyboardInterrupt:
        print("\nSimulador detenido")


if __name__ == "__main__":
    main()
