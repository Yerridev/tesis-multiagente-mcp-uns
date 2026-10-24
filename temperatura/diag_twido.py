"""
Diagnóstico del PLC Twido - Módulo de Temperatura MCT-09/001 (Inducontrol)
PLC: 192.168.114.10  |  Modbus TCP puerto 502
%MWi = holding register i  |  %Mi = coil i  (base 0)

Uso:
  python diag_twido.py               -> solo lectura (por defecto, seguro)
  python diag_twido.py --loop        -> lectura cada 1 s (Ctrl+C para salir)
  python diag_twido.py --arrancar-pc [--sp 30 --variador 50 --kp 5000 --ti 10 --td 10]
        -> carga parámetros PID + variador y da el pulso de INICIO en modo PC (%M30=1)
  python diag_twido.py --detener-pc  -> DETIENE: %M30=0 y variador a 0

Requisito: pip install pymodbus
Las opciones de escritura piden confirmación y solo deben usarse con
autorización del responsable del laboratorio.
"""
import sys
import time
from pymodbus.client import ModbusTcpClient

IP, PORT = "192.168.114.10", 502
UNITS = (1, 255)          # Twido suele responder a 1; si no, a 255
ESCALA = 100 / 4095       # 4-20 mA -> 0..4095 -> 0..100 °C (verificar con termómetro)


def _call(fn, *args, unit, **kw):
    """Compatibilidad pymodbus 3.x (slave / device_id / unit)."""
    for key in ("device_id", "slave", "unit"):
        try:
            return fn(*args, **kw, **{key: unit})
        except TypeError:
            continue
    return fn(*args, **kw)


def detectar_unit(c):
    for u in UNITS:
        r = _call(c.read_holding_registers, 0, count=1, unit=u)
        if not r.isError():
            return u
    return None


_METODO_BITS = None   # se detecta una vez


def _leer_bits(c, u):
    """Prueba varias formas de leer %M0..%M47 (el Twido rechazó FC01 x64)."""
    global _METODO_BITS
    intentos = [("FC01 coils x48", c.read_coils, 48),
                ("FC01 coils x40", c.read_coils, 40),
                ("FC01 coils x32", c.read_coils, 32),
                ("FC02 discretas x48", c.read_discrete_inputs, 48)]
    if _METODO_BITS:
        intentos = [t for t in intentos if t[0] == _METODO_BITS] + intentos
    for nombre, fn, n in intentos:
        r = _call(fn, 0, count=n, unit=u)
        if not r.isError():
            if _METODO_BITS != nombre:
                print(f"[bits leídos con {nombre}]")
                _METODO_BITS = nombre
            bits = list(r.bits) + [False] * 64
            return bits[:64]
        print(f"[{nombre} falló: {r}]")
    # Último recurso: bit a bit (lento, pero dice qué direcciones existen)
    bits = []
    for i in range(48):
        r = _call(c.read_coils, i, count=1, unit=u)
        bits.append(None if r.isError() else bool(r.bits[0]))
    print("[lectura bit a bit; None = dirección rechazada]")
    return bits + [None] * 16


def leer(c, u):
    hr = _call(c.read_holding_registers, 0, count=24, unit=u)
    pid = _call(c.read_holding_registers, 100, count=11, unit=u)
    if hr.isError() or pid.isError():
        raise RuntimeError(f"Error Modbus registros: {hr} | {pid}")
    return hr.registers, pid.registers, _leer_bits(c, u)


def informe(hr, pid, m):
    s = lambda b: "?" if b is None else ("1" if b else "0")
    print("=" * 64)
    print(time.strftime("%H:%M:%S"), "PLC Twido temperatura")
    print("-" * 64)
    print(f"T principal  %MW0 = {hr[0]:5d} raw -> {hr[0]*ESCALA:6.2f} °C")
    print(f"T enfriador  %MW1 = {hr[1]:5d} raw -> {hr[1]*ESCALA:6.2f} °C")
    print(f"Variador     %MW10= {hr[10]:5d} (salida analógica al Altivar)")
    print(f"SP %MW100={pid[0]} (= {pid[0]*ESCALA:.1f} °C)  Kp %MW101={pid[1]}  Ti %MW102={pid[2]}  "
          f"Td %MW103={pid[3]}  Salida PID %MW110={pid[10]}")
    print("-" * 64)
    print(f"Entradas: SelPC M0={s(m[0])} SelHMI M1={s(m[1])} "
          f"HabEnf M2={s(m[2])} DeshabEnf M3={s(m[3])}")
    print(f"Niveles : TP alto M4={s(m[4])} TP bajo M5={s(m[5])} "
          f"TE alto M6={s(m[6])} TE bajo M7={s(m[7])}")
    print(f"Fallas  : M20(TP)={s(m[20])} M21(TE)={s(m[21])}")
    print(f"Inicio  : PC M30={s(m[30])} HMI M32={s(m[32])} "
          f"| Lazo PC M31={s(m[31])} Lazo HMI M33={s(m[33])}")
    print(f"Salidas : Funcionando M12={s(m[12])} Variador M13={s(m[13])} "
          f"Resist M14={s(m[14])} Enfriador M19={s(m[19])}")
    print("-" * 64)
    print("DIAGNÓSTICO:")
    ok = True
    if not m[0] and not m[1]:
        ok = False
        print(" ✗ Selector CONTROLADOR en 0: ponerlo en HMI o PC (M0/M1 = 0).")
    if m[0] and m[1]:
        ok = False
        print(" ✗ M0 y M1 activos a la vez: revisar cableado del selector.")
    if m[20]:
        ok = False
        print(" ✗ Bloqueo TANQUE PRINCIPAL (M20): " +
              ("nivel ALTO activado. " if m[4] else "") +
              ("nivel BAJO no detectado (falta agua o flotador invertido)." if not m[5] else ""))
    if m[21]:
        ok = False
        print(" ✗ Bloqueo TANQUE ENFRIADOR (M21): " +
              ("nivel ALTO activado. " if m[6] else "") +
              ("nivel BAJO no detectado (falta agua o flotador invertido)." if not m[7] else ""))
    if ok and not (m[31] or m[33]):
        if m[1]:
            print(" • Permisos OK en modo HMI, pero falta INICIO (M32=0): la HMI no está")
            print("   escribiendo al PLC -> cadena HMI -> PC(.100) -> PLC rota.")
        if m[0]:
            print(" • Permisos OK en modo PC, pero falta INICIO (M30=0): el SCADA de la PC")
            print("   no está escribiendo al PLC (I/O Server Modbus / LabVIEW DSC).")
    if m[31] or m[33]:
        print(" ✓ Lazo en marcha (" + ("PC" if m[31] else "HMI") + ").")
        if hr[10] == 0:
            print(" • Variador en 0 (%MW10=0): la bomba no gira. Subir la velocidad.")
        if pid[1] == 0:
            print(" • Kp=0 (%MW101): el PID no calienta. Cargar Kp=5000, Ti=10, Td=10.")
        if pid[0] == 0:
            print(" • SP=0 (%MW100): con SP en 0 la resistencia no enciende.")
    print("=" * 64)


def _arg(args, nombre, defecto):
    if nombre in args:
        return float(args[args.index(nombre) + 1])
    return defecto


def _escribir_bit(c, u, addr, valor):
    r = _call(c.write_coil, addr, valor, unit=u)            # FC05
    if r.isError():
        print(f"[FC05 falló: {r}; probando FC15]")
        r = _call(c.write_coils, addr, [valor], unit=u)     # FC15
    if r.isError():
        raise RuntimeError(f"No se pudo escribir %M{addr}: {r}")


def _escribir_reg(c, u, addr, valores):
    r = _call(c.write_registers, addr, valores, unit=u)     # FC16
    if r.isError():
        print(f"[FC16 falló: {r}; probando FC06]")
        for i, v in enumerate(valores):
            r = _call(c.write_register, addr + i, v, unit=u)
            if r.isError():
                raise RuntimeError(f"No se pudo escribir %MW{addr+i}: {r}")


def confirmar(msg):
    print(msg)
    return input("Escribe SI para continuar: ").strip().upper() == "SI"


def main():
    c = ModbusTcpClient(IP, port=PORT, timeout=3)
    if not c.connect():
        print(f"No conecta a {IP}:{PORT}. Revisar cable/IP/firewall.")
        return
    u = detectar_unit(c)
    if u is None:
        print("Conecta por TCP pero el PLC no responde a Modbus (unit 1 ni 255).")
        c.close()
        return
    print(f"Conectado a {IP}:{PORT} (unit id {u})")
    args = sys.argv[1:]
    try:
        if "--arrancar-pc" in args or "--detener-pc" in args:
            hr, pid, m = leer(c, u)
            informe(hr, pid, m)
            valor = "--arrancar-pc" in args
            if valor and not m[0]:
                print("El selector no está en PC (M0=0). Gíralo a PC primero.")
                return
            if not valor:
                if confirmar("Se escribirá %M30=0 (DETENER) y variador %MW10=0."):
                    _escribir_bit(c, u, 30, False)
                    _escribir_reg(c, u, 10, [0])
                    time.sleep(1.5)
                    informe(*leer(c, u))
                return
            sp_c = _arg(args, "--sp", 30)          # °C
            var_p = _arg(args, "--variador", 50)   # %
            kp = int(_arg(args, "--kp", 5000))
            ti = int(_arg(args, "--ti", 10))
            td = int(_arg(args, "--td", 10))
            if not 15 <= sp_c <= 50:
                print("SP fuera del rango de operación del manual (15-50 °C).")
                return
            sp = int(round(sp_c * 4095 / 100))     # igual que el SCADA original: SP en cuentas 0..4095 (0..100 °C)
            var = int(round(var_p / 100 * 4095))   # salida analógica 0..4095 = 0..10 V
            msg = (f"Se escribirá en el PLC:\n"
                   f"  %MW100 SP={sp} ({sp_c} °C)  %MW101 Kp={kp}  %MW102 Ti={ti}  %MW103 Td={td}\n"
                   f"  %MW10 variador={var} ({var_p} %)\n"
                   f"  %M30 pulso de INICIO (modo PC)")
            if confirmar(msg):
                _escribir_reg(c, u, 100, [sp, kp, ti, td])
                _escribir_reg(c, u, 10, [var])
                _escribir_bit(c, u, 30, False)
                time.sleep(0.5)
                _escribir_bit(c, u, 30, True)       # flanco 0 -> 1
                for _ in range(5):
                    time.sleep(1)
                    informe(*leer(c, u))
            return
        from collections import deque
        hist0, hist1 = deque(maxlen=60), deque(maxlen=60)
        t_ini, prom_ini = time.time(), None
        while True:
            hr, pid, m = leer(c, u)
            informe(hr, pid, m)
            if "--loop" not in args:
                break
            hist0.append(hr[0] * ESCALA)
            hist1.append(hr[1] * ESCALA)
            p0, p1 = sum(hist0) / len(hist0), sum(hist1) / len(hist1)
            if prom_ini is None and len(hist0) == hist0.maxlen:
                prom_ini = (p0, time.time())
            tend = ""
            if prom_ini:
                mins = (time.time() - prom_ini[1]) / 60
                if mins > 0.5:
                    tend = f" | tendencia TP: {(p0 - prom_ini[0]) / mins:+.3f} °C/min"
            print(f"PROMEDIO 60 s -> TP {p0:6.2f} °C  TE {p1:6.2f} °C{tend}")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        c.close()


if __name__ == "__main__":
    main()
