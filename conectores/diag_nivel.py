#!/usr/bin/env python3
"""
Monitor de diagnóstico del lazo de nivel del MCN-09/001 (SOLO LECTURA).

Lee el MicroLogix 1100 por EtherNet/IP (PCCC) y muestra, en vivo, el estado
completo del lazo: selector, protecciones, bits de arranque, PID, variador y
sensor. NO escribe nada en el PLC.

Uso:
    python diag_nivel.py                     # 30 s, 1 muestra/s
    python diag_nivel.py --segundos 300      # 5 min
    python diag_nivel.py --plc 192.168.114.9

Lecturas (rutas del programa, ver 07_PLC_RSLOGIX/ladder_control_nivel_micrologix1100.md):
    I:0/0 MODO_REMOTO · I:0/1 MODO_LOCAL · I:0/2 switch nivel bajo T1
    O:0/2 SIST_FUNCIONANDO · O:0/3 arranque variador · O:1/0 ref. al variador
    B3:0/3 PC_HMI · B3:0/4 START_PC · B3:0/10 START_REMOTO · B3:0/14 flanco start
    N7:4  PV del PID (= I:1.1, el sensor) · N7:5 SP (cuentas) · N7:8/9/10 PID
    N7:14 CV del PID · N7:0 ref. al variador en PC
    I:1.1 sensor ultrasonico (0-10 V del 1762-IF2OF2)

Interpretacion clave:
    cm  = (16348 - N7:4) / 400        (calibracion de 4 puntos, 20-oct-2026)
    error = N7:4 - N7:5               (el PID compara CUENTAS, no cm)
    Si N7:4 esta por DEBAJO de N7:5, el PID satura la salida ABAJO (O:1.0 = 0)
    y el variador se para: la bomba "muere".
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

from pycomm3 import SLCDriver

CAL_CERO = 16348.0
CUENTAS_POR_CM = 400.0
LIMITE_SENSOR_RAW = 300      # por debajo, el sensor esta saturado (~40.9 cm)


def bits(v: int) -> str:
    return format(v, "016b")


def main() -> int:
    ap = argparse.ArgumentParser(description="Monitor de diagnostico del lazo de nivel (solo lectura)")
    ap.add_argument("--plc", default="192.168.114.9")
    ap.add_argument("--segundos", type=float, default=30.0)
    ap.add_argument("--periodo", type=float, default=1.0)
    a = ap.parse_args()

    plc = SLCDriver(a.plc)
    plc.open()
    print(f"[{datetime.now():%H:%M:%S}] Conectado al PLC {a.plc} · solo lectura · {a.segundos:.0f} s\n")
    try:
        fin = time.time() + a.segundos
        while time.time() < fin:
            t0 = time.time()
            try:
                i0 = plc.read("I:0.0").value
                o0 = plc.read("O:0.0").value
                o1 = plc.read("O:1.0").value
                b3 = plc.read("B3:0{2}").value
                n7 = plc.read("N7:0{21}").value
                i11 = plc.read("I:1.1").value
            except Exception as ex:  # noqa: BLE001
                print(f"[{datetime.now():%H:%M:%S}] error de lectura: {ex}")
                time.sleep(2)
                continue

            pv, sp, cv, ref_pc = n7[4], n7[5], n7[14], n7[0]
            kc, ti, td = n7[8], n7[9], n7[10]
            cm = (CAL_CERO - pv) / CUENTAS_POR_CM
            cm_sp = (CAL_CERO - sp) / CUENTAS_POR_CM
            error = pv - sp

            remoto = bool(i0 & 1)
            local = bool(i0 & 2)
            bajo_t1 = bool(i0 & 4)
            alarma = bool(o0 & 1) or bool(o0 & 2)
            sist = bool(o0 & 4)
            var_arr = bool(o0 & 8)
            pc_hmi = bool(b3[0] & 8)
            start_pc = bool(b3[0] & 16)
            start_rem = bool(b3[0] & 1024)
            flanco = bool(b3[0] & 16384)

            print(f"[{datetime.now():%H:%M:%S}]")
            print(f"   selector      REMOTO={remoto} LOCAL={local} | switch nivel bajo T1={bajo_t1} | alarma={alarma}")
            print(f"   bits          PC_HMI={pc_hmi} START_PC={start_pc} START_REMOTO={start_rem} flanco={flanco}  (B3:0={bits(b3[0])})")
            print(f"   salida        SIST_FUNCIONANDO={sist} arranque_variador={var_arr}")
            print(f"   SENSOR  I:1.1={i11} cuentas  ->  N7:4={pv}  =  {cm:+.1f} cm"
                  f"   {'[SATURADO: el sensor no mide]' if pv < LIMITE_SENSOR_RAW else ''}")
            print(f"   SP      N7:5={sp} = {cm_sp:+.1f} cm   |   error PID (PV-SP) = {error:+d} cuentas"
                  f"   {'[NEGATIVO -> PID satura ABAJO -> variador a 0 -> la bomba se para]' if error < 0 else '[positivo -> PID manda variador]'} ")
            print(f"   PID     Kc={kc} Ti={ti} Td={td}   CV N7:14={cv}   ref variador N7:0={ref_pc}   O:1.0={o1}")
            print()
            time.sleep(max(0.05, a.periodo - (time.time() - t0)))
    finally:
        plc.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
