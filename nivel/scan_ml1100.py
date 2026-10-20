"""
Escaner SOLO LECTURA del mapa de datos del MicroLogix 1100 (modulo nivel).
Descubre que archivos de datos existen (B, N, F, T, C, L, ST) y cuantos
elementos tiene cada uno, luego los lee completos y guarda un JSON.

Uso:
    python scan_ml1100.py                  # escaneo completo + mapa_ml1100_*.json
    python scan_ml1100.py --watch 2        # tras el escaneo, relee cada 2 s y
                                           # muestra SOLO lo que cambia

REGLA: no se usa plc.write en ningun lugar.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from pycomm3 import SLCDriver

IP = "192.168.114.9"
MAX_ELEMS = 256          # limite por archivo en MicroLogix
CHUNK = 30               # lectura por bloques (tamano seguro de paquete)

# (prefijo, rango de numeros de archivo a explorar)
CANDIDATES = [("B", range(3, 30)), ("N", range(7, 40)), ("F", range(8, 40)),
              ("L", range(9, 40))]
# Temporizadores/contadores: se leen sus campos .ACC/.PRE/.EN/.DN
TIMER_FILES = [("T", range(4, 20)), ("C", range(5, 20))]


def ok(plc, addr):
    try:
        t = plc.read(addr)
        return t.error is None, (t.value if t.error is None else None)
    except Exception:
        return False, None


def file_size(plc, ref):
    """Numero de elementos de un archivo (0 si no existe). Busqueda binaria."""
    if not ok(plc, f"{ref}:0")[0]:
        return 0
    lo, hi = 0, MAX_ELEMS - 1           # lo existe; buscar ultimo indice valido
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if ok(plc, f"{ref}:{mid}")[0]:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def read_file(plc, ref, n):
    vals = []
    for start in range(0, n, CHUNK):
        cnt = min(CHUNK, n - start)
        good, v = ok(plc, f"{ref}:{start}{{{cnt}}}")
        if not good:                    # fallback elemento a elemento
            v = [ok(plc, f"{ref}:{i}")[1] for i in range(start, start + cnt)]
        vals.extend(v if isinstance(v, list) else [v])
    return vals


def read_timers(plc, ref, n):
    out = []
    for i in range(n):
        row = {}
        for fld in ("PRE", "ACC", "EN", "TT", "DN", "CU", "CD"):
            good, v = ok(plc, f"{ref}:{i}.{fld}")
            if good:
                row[fld] = v
        out.append(row)
    return out


def scan(plc):
    mapa = {"io": {}, "files": {}, "sizes": {}}
    for addr in ("I:0.0{2}", "O:0.0{2}", "I:1.0{6}", "O:1.0{2}"):
        good, v = ok(plc, addr)
        mapa["io"][addr] = v if good else "no existe"

    try:
        mapa["file_directory"] = str(plc.get_file_directory())
    except Exception as e:
        mapa["file_directory"] = f"no disponible ({e!r})"

    for pref, rng in CANDIDATES:
        for num in rng:
            ref = f"{pref}{num}"
            n = file_size(plc, ref)
            if n:
                mapa["sizes"][ref] = n
                mapa["files"][ref] = read_file(plc, ref, n)
                print(f"  {ref:<5} {n:>3} elementos")

    for pref, rng in TIMER_FILES:
        for num in rng:
            ref = f"{pref}{num}"
            if ok(plc, f"{ref}:0.ACC")[0]:
                n = 1
                while n < MAX_ELEMS and ok(plc, f"{ref}:{n}.ACC")[0]:
                    n += 1
                mapa["sizes"][ref] = n
                mapa["files"][ref] = read_timers(plc, ref, n)
                print(f"  {ref:<5} {n:>3} elementos (T/C)")
    return mapa


def flat(mapa):
    """Diccionario plano direccion -> valor (para detectar cambios)."""
    out = {}
    for addr, v in mapa["io"].items():
        base = addr.split("{")[0]
        f, w = base.rsplit(".", 1)
        for i, x in enumerate(v if isinstance(v, list) else [v]):
            out[f"{f}.{int(w) + i}"] = x
    for ref, vals in mapa["files"].items():
        for i, x in enumerate(vals):
            if isinstance(x, dict):
                for k, y in x.items():
                    out[f"{ref}:{i}.{k}"] = y
            else:
                out[f"{ref}:{i}"] = x
    return out


def fmt(v):
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v} (0b{v & 0xFFFF:016b})"
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=float, default=0)
    args = ap.parse_args()

    with SLCDriver(IP) as plc:
        print(f"Procesador: {plc.get_processor_type()}\nEscaneando archivos de datos...")
        mapa = scan(plc)

        out = Path(__file__).with_name(f"mapa_ml1100_{datetime.now():%Y%m%d_%H%M%S}.json")
        out.write_text(json.dumps(mapa, indent=2, default=str), encoding="utf-8")
        print(f"\nE/S: {mapa['io']}")
        print(f"Mapa guardado en {out.name}")

        if args.watch <= 0:
            return
        prev = flat(mapa)
        print(f"\nModo watch cada {args.watch}s (Ctrl+C para salir). Solo cambios:")
        while True:
            time.sleep(args.watch)
            m = {"io": {}, "files": {}}
            for addr in mapa["io"]:
                good, v = ok(plc, addr)
                m["io"][addr] = v if good else "no existe"
            for ref, n in mapa["sizes"].items():
                m["files"][ref] = (read_timers(plc, ref, n) if ref[0] in "TC"
                                   else read_file(plc, ref, n))
            cur = flat(m)
            ts = datetime.now().strftime("%H:%M:%S")
            for k, v in cur.items():
                if prev.get(k) != v:
                    print(f"  {ts}  {k:<12} {fmt(prev.get(k))}  ->  {fmt(v)}")
            prev = cur


if __name__ == "__main__":
    main()
