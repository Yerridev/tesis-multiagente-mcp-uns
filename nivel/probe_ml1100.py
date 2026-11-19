"""
Sonda SOLO LECTURA para el MicroLogix 1100 del modulo de nivel (MCN-09/001).
Protocolo: EtherNet/IP (PCCC) puerto 44818 via pycomm3.SLCDriver.

Uso:
    pip install pycomm3
    python probe_ml1100.py                 # una lectura completa + snapshot JSON
    python probe_ml1100.py --watch 2       # relee cada 2 s y marca (*) lo que cambia

REGLA: este script NO escribe en el PLC (no se usa plc.write en ningun lugar).
"""
import argparse
import json
import socket
import time
from datetime import datetime
from pathlib import Path

from pycomm3 import SLCDriver

IP = "192.168.114.9"
PORT = 44818

# Bloques a explorar. Si alguno no existe en el programa, se reporta y se sigue.
ADDRESSES = [
    "I:0.0",        # entradas digitales embebidas
    "O:0.0",        # salidas digitales embebidas
    "I:1.0{4}",     # 1762-IF2OF2: canales analogicos de entrada + estado
    "O:1.0{2}",     # 1762-IF2OF2: salidas analogicas
    "B3:0{8}",      # bits internos (Local/Remoto, marcha, alarmas)
    "N7:0{60}",     # enteros (escalados, setpoint, intercambio con HMI/PC)
    "F8:0{30}",     # flotantes (PID, escalas en %, cm)
]


def tcp_ok(ip, port, timeout=3):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError as e:
        print(f"[X] Sin conexion TCP a {ip}:{port} -> {e}")
        return False


def read_all(plc):
    out = {}
    for addr in ADDRESSES:
        try:
            tag = plc.read(addr)
            out[addr] = {"error": str(tag.error)} if tag.error else tag.value
        except Exception as e:  # direccion inexistente, tipo, etc.
            out[addr] = {"error": repr(e)}
    return out


def as_list(v):
    return v if isinstance(v, list) else [v]


def show(data, prev=None):
    for addr, val in data.items():
        if isinstance(val, dict):
            print(f"  {addr:<10} ERROR {val['error']}")
            continue
        old = None
        if prev and not isinstance(prev.get(addr), dict):
            old = as_list(prev[addr])
        parts = []
        for i, v in enumerate(as_list(val)):
            mark = "*" if old is not None and i < len(old) and old[i] != v else ""
            parts.append(f"[{i}]={v}{mark}")
        print(f"  {addr:<10} " + "  ".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=float, default=0, help="segundos entre lecturas")
    args = ap.parse_args()

    print(f"1) Probando TCP {IP}:{PORT} (EtherNet/IP)...")
    if not tcp_ok(IP, PORT):
        print("   -> Revisa: ping, IP de tu laptop en 192.168.114.x, cable al switch.")
        return
    print("   OK\n2) Conectando con SLCDriver (solo lectura)...")

    with SLCDriver(IP) as plc:
        try:
            print(f"   Procesador: {plc.get_processor_type()}")
        except Exception as e:
            print(f"   (no se pudo leer tipo de procesador: {e!r})")

        data = read_all(plc)
        print("\n3) Lectura:")
        show(data)

        snap = Path(__file__).with_name(f"snapshot_ml1100_{datetime.now():%Y%m%d_%H%M%S}.json")
        snap.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"\n   Snapshot guardado en {snap.name}")

        prev = data
        while args.watch > 0:
            time.sleep(args.watch)
            data = read_all(plc)
            print(f"\n--- {datetime.now():%H:%M:%S}  (* = cambio) ---")
            show(data, prev)
            prev = data


if __name__ == "__main__":
    main()
