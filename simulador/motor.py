"""Bucle comun de simulacion: avanza el tiempo (con aceleracion), aplica escenarios y ejecuta el scan del PLC."""
from __future__ import annotations

import asyncio
import time
from typing import Callable

from .escenarios import Reproductor

PASO = 0.1  # s simulados por sub-paso


async def bucle(plc, aplicar: Callable[[dict], None], escenario: dict | None,
                acelerar: float, log: float, estado_red: Callable[[], str]):
    rep = Reproductor(escenario)
    t_sim, ultimo_log = 0.0, -1e9
    reloj = time.monotonic()
    while True:
        await asyncio.sleep(PASO / acelerar)
        ahora = time.monotonic()
        avanzar = (ahora - reloj) * acelerar
        reloj = ahora
        while avanzar > 1e-9:
            dt = min(PASO, avanzar)
            for ev in rep.pendientes(t_sim):
                aplicar(ev)
                print(f"  >> evento t={ev['t']} s: {ev['accion']} = {ev.get('valor')}"
                      + (f"  ({ev['nota']})" if ev.get("nota") else ""))
            plc.scan(dt)
            t_sim += dt
            avanzar -= dt
        if t_sim - ultimo_log >= log:
            ultimo_log = t_sim
            m, s = divmod(int(t_sim), 60)
            print(f"[{m:03d}:{s:02d}] {plc.resumen()}  plc={estado_red()}", flush=True)


def argumentos_comunes(ap, puerto: int):
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 para aceptar conexiones de otras maquinas/contenedores")
    ap.add_argument("--port", type=int, default=puerto)
    ap.add_argument("--acelerar", type=float, default=1.0, help="factor de tiempo (10 = 10 veces mas rapido)")
    ap.add_argument("--escenario", help="archivo JSON de simulador/escenarios/")
    ap.add_argument("--semilla", type=int, default=None, help="semilla del ruido (pruebas repetibles)")
    ap.add_argument("--log", type=float, default=10.0, help="segundos simulados entre lineas de estado")
    ap.add_argument("--broker", default="127.0.0.1", help="MQTT para las llaves manuales de la planta simulada")
    ap.add_argument("--puerto-mqtt", type=int, default=1883)
    ap.add_argument("--sin-llaves", action="store_true", help="sin llaves manuales (comportamiento anterior)")
    ap.add_argument("--nivel-inicial", type=float, default=None, help="%% inicial de los tanques (por defecto 5 %%: hay que llenarlos)")


def con_llaves(plc, clase, a):
    """Envuelve el PLC con las llaves manuales de la planta simulada (salvo --sin-llaves)."""
    if a.sin_llaves:
        return plc, None
    from .llaves import ConLlaves
    ll = clase(a.broker, a.puerto_mqtt, a.nivel_inicial)
    return ConLlaves(plc, ll), ll
