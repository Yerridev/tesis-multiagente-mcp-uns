"""Simulador del modulo de caudal MCC-09: S7-200 virtual (protocolo S7, puerto 102) + planta hidraulica.

Uso:
    python -m simulador.caudal                          # escucha en 127.0.0.1:102
    python -m simulador.caudal --escenario simulador/escenarios/caudal_fallas.json --acelerar 5

Conector real contra el simulador (sin --source-ip, que solo exige el CP243-1 real):
    python conectores/conector_edge_s7200.py --plc 127.0.0.1 --local-tsap 1000 --remote-tsap 1000 --broker 127.0.0.1
"""
from __future__ import annotations

import argparse
import asyncio

import snap7
from snap7.type import SrvArea
from snap7.util import set_bool, set_int, set_real

from .escenarios import cargar
from .motor import argumentos_comunes, bucle
from .plantas.caudal import PlantaCaudal
from .plcs.s7200_caudal import S7200Caudal

ACCIONES = {"selector", "mando", "agua_t1", "nivel_alto", "arranque_local", "potenciometro_pct",
            "sensor_congelado", "obstruccion", "plc_desconectado", "escribir_v_real", "escribir_m_bit", "escribir_mw"}


class ServidorS7:
    def __init__(self, plc: S7200Caudal, host: str, port: int):
        self.plc, self.host, self.port = plc, host, port
        self.conectado = False
        self.srv = None

    def iniciar(self):
        self.srv = snap7.server.Server(log=False)
        self.srv.register_area(SrvArea.DB, 1, self.plc.V)   # memoria V del S7-200 = DB1
        self.srv.register_area(SrvArea.MK, 0, self.plc.M)
        self.srv.register_area(SrvArea.PE, 0, self.plc.I)
        self.srv.register_area(SrvArea.PA, 0, self.plc.Q)
        self.srv.start_to(self.host, self.port)
        self.conectado = True

    def desconectar(self, valor: bool):
        if valor and self.conectado:
            self.srv.stop(); self.srv.destroy(); self.conectado = False
        elif not valor and not self.conectado:
            self.iniciar()


def aplicar(ev: dict, plc: S7200Caudal, srv: ServidorS7):
    a, v = ev["accion"], ev.get("valor")
    if a in ("selector", "mando", "agua_t1", "nivel_alto", "arranque_local", "potenciometro_pct"):
        setattr(plc.ent, a, v)
    elif a == "sensor_congelado":
        plc.planta.e.sensor_congelado = bool(v)
    elif a == "obstruccion":
        plc.planta.e.obstruccion = float(v)
    elif a == "plc_desconectado":
        srv.desconectar(bool(v))
    elif a == "escribir_v_real":
        set_real(plc.V, int(ev["direccion"]), float(v))
    elif a == "escribir_m_bit":
        set_bool(plc.M, int(ev["byte"]), int(ev["bit"]), bool(v))
    elif a == "escribir_mw":
        set_int(plc.M, int(ev["direccion"]), int(v))


async def ejecutar(a):
    plc = S7200Caudal(PlantaCaudal(semilla=a.semilla))
    srv = ServidorS7(plc, a.host, a.port)
    srv.iniciar()
    escenario = cargar(a.escenario, ACCIONES) if a.escenario else None
    print(f"S7-200 virtual (caudal) en {a.host}:{a.port}  |  aceleracion x{a.acelerar}"
          + (f"  |  escenario: {escenario.get('nombre')}" if escenario else ""))
    try:
        await bucle(plc, lambda ev: aplicar(ev, plc, srv), escenario, a.acelerar, a.log,
                    lambda: "OK" if srv.conectado else "CAIDO")
    finally:
        if srv.conectado:
            srv.srv.stop()


def main():
    ap = argparse.ArgumentParser(description="Simulador del modulo de caudal (S7-200 virtual)")
    argumentos_comunes(ap, 102)
    try:
        asyncio.run(ejecutar(ap.parse_args()))
    except KeyboardInterrupt:
        print("\nSimulador detenido")


if __name__ == "__main__":
    main()
