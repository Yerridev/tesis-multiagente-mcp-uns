#!/usr/bin/env python3
"""TEST ENFRIAR - modulo de temperatura (Twido 192.168.114.10).

Que hace (2 minutos):
  1. Revisa selector en PC (%M0=1, %M1=0) y que no haya alarmas de nivel (%M20/%M21).
  2. Guarda setpoint (%MW100) y velocidad de bomba (%MW10) originales.
  3. Setpoint = 0 C  -> el PID apaga la resistencia y el enfriador queda pedido.
  4. Bomba al 80 % (%MW10 = 3276) -> variador / recirculacion.
  5. Inicio PC (%M30 = 1) -> marcha (%M12/%M13 -> %Q0.2/%Q0.3).
  6. El enfriador (%M19 -> %Q0.10) prende solo tras 2 min (temporizador del PLC).
  7. Registra cada 1 s en pantalla y en logs\test-enfriar-FECHA.csv.
  8. Al final (o con Ctrl+C): %M30 = 0 y restaura setpoint y velocidad.
"""
import csv, os, sys, time
from datetime import datetime
from pymodbus.client import ModbusTcpClient

PLC = "192.168.114.10"
DURACION_S = 120
BOMBA_RAW = 3276          # 80 % de 4095
SP_RAW = 0                # 0 C
ESC = 100 / 4095

def call(fn, *a, **kw):
    for k in ("device_id", "slave", "unit"):
        try: return fn(*a, **kw, **{k: 1})
        except TypeError: pass
    return fn(*a, **kw)

c = ModbusTcpClient(PLC, port=502, timeout=4)
def reg(a):
    r = call(c.read_holding_registers, a, count=1)
    if r.isError(): raise IOError(f"leer %MW{a}: {r}")
    return int(r.registers[0])
def bit(a):
    r = call(c.read_coils, a, count=1)
    if r.isError(): raise IOError(f"leer %M{a}: {r}")
    return int(bool(r.bits[0]))
def wreg(a, v):
    r = call(c.write_register, a, int(v))
    if r.isError(): raise IOError(f"escribir %MW{a}: {r}")
    time.sleep(.3); return reg(a)
def wbit(a, v):
    r = call(c.write_coil, a, bool(v))
    if r.isError(): raise IOError(f"escribir %M{a}: {r}")
    time.sleep(.3); return bit(a)
def T(raw): return raw * ESC

print("=" * 70); print(" TEST ENFRIAR - 2 minutos - Twido", PLC); print("=" * 70)
print("[1] Conectando..."); 
if not c.connect(): print("   NO conecta al PLC. Revisa red (bat 01)."); sys.exit(1)
print("   conectado")

print("[2] Revisando condiciones:")
m0, m1, a1, a2 = bit(0), bit(1), bit(20), bit(21)
print(f"   selector PC %M0={m0}  HMI %M1={m1}  alarma nivel principal %M20={a1}  enfriador %M21={a2}")
if m0 != 1 or m1 != 0:
    print("   ABORTO: pon el selector CONTROLADOR en PC."); sys.exit(1)
if a1 or a2:
    print("   ABORTO: hay alarma de nivel (tanque muy bajo o muy alto). El PLC no deja arrancar."); sys.exit(1)

sp0, vel0, m30_0 = reg(100), reg(10), bit(30)
print(f"   setpoint actual %MW100={sp0} ({T(sp0):.1f} C)  bomba %MW10={vel0} ({vel0*ESC:.0f} %)  inicio %M30={m30_0}")
print(f"   T principal={T(reg(0)):.1f} C   T enfriador={T(reg(1)):.1f} C")

os.makedirs("logs", exist_ok=True)
ruta = os.path.join("logs", f"test-enfriar-{datetime.now():%Y%m%d-%H%M%S}.csv")
f = open(ruta, "w", newline="", encoding="utf-8"); w = csv.writer(f)
w.writerow(["t_s", "hora", "T_principal_C", "T_enfriador_C", "raw_MW0", "raw_MW1",
            "bomba_pct", "marcha_M12", "marcha_M13", "resistencia_M14", "timer2min_M44", "enfriador_M19", "M30"])

prim = None; vio = {"M12": 0, "M14": 0, "M19": 0}
try:
    print("[3] Setpoint = 0 C (apaga resistencia, pide enfriador)...  leido:", wreg(100, SP_RAW))
    print("[4] Bomba al 80 %...  leido %MW10:", wreg(10, BOMBA_RAW))
    print("[5] Inicio PC %M30=1...  leido:", wbit(30, 1))
    time.sleep(1)
    if bit(30) == 0: print("   %M30 se cayo: el PLC lo borro (alarma de nivel)."); raise SystemExit(1)
    print("[6] Registrando 2 min (el enfriador prende a los ~2 min). Ctrl+C para cortar.\n")
    print("  t(s)  T_princ  T_enfr  bomba%  marcha  resist  timer2m  enfriador")
    t0 = time.time()
    while (t := time.time() - t0) < DURACION_S:
        r0, r1, vel = reg(0), reg(1), reg(10)
        b = {k: bit(n) for k, n in (("M12", 12), ("M13", 13), ("M14", 14), ("M44", 44), ("M19", 19), ("M30", 30))}
        for k in vio: vio[k] |= b[k]
        if prim is None: prim = (T(r0), T(r1))
        print(f"  {t:5.0f}  {T(r0):6.1f}  {T(r1):6.1f}  {vel*ESC:5.0f}   {b['M12']:^6}  {b['M14']:^6}  {b['M44']:^7}  {b['M19']:^9}")
        w.writerow([round(t, 1), datetime.now().strftime("%H:%M:%S"), round(T(r0), 2), round(T(r1), 2), r0, r1,
                    round(vel*ESC), b["M12"], b["M13"], b["M14"], b["M44"], b["M19"], b["M30"]]); f.flush()
        if b["M30"] == 0: print("  %M30 se cayo (alarma de nivel). Corto."); break
        time.sleep(max(0, 1 - (time.time() - t0 - t) % 1))
except KeyboardInterrupt:
    print("\n  Cortado por el usuario.")
finally:
    print("\n[7] Dejando todo como estaba:")
    for paso, fn in (("parar %M30=0", lambda: wbit(30, 0)),
                     (f"setpoint %MW100={sp0}", lambda: wreg(100, sp0)),
                     (f"bomba %MW10={vel0}", lambda: wreg(10, vel0))):
        try: print(f"   {paso} -> leido {fn()}")
        except Exception as e: print(f"   {paso} -> ERROR {e}  (hazlo manual / selector a 0)")
    f.close()

if prim:
    fin = (T(reg(0)), T(reg(1)))
    print("\n" + "=" * 70); print(" RESUMEN")
    print(f"   T principal: {prim[0]:.1f} -> {fin[0]:.1f} C  (cambio {fin[0]-prim[0]:+.1f})")
    print(f"   T enfriador: {prim[1]:.1f} -> {fin[1]:.1f} C  (cambio {fin[1]-prim[1]:+.1f})")
    print(f"   marcha bomba (%M12) se activo : {'SI' if vio['M12'] else 'NO'}")
    print(f"   enfriador (%M19) se activo    : {'SI' if vio['M19'] else 'NO'}")
    print(f"   resistencia (%M14) prendio    : {'SI  <-- no deberia' if vio['M14'] else 'NO (bien)'}")
    print("   Si el PLC dice marcha=1 y la bomba NO gira -> revisar variador Altivar / contactor / termico.")
    print("   Si el agua sigue calentando con resistencia=NO -> SSR en corto.")
print("\n Log:", os.path.abspath(ruta))
c.close()
