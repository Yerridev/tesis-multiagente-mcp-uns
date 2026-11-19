# Sondeo SOLO LECTURA del cFP-2200 (modulo de presion) desde la laptop
# Hace ping y prueba los puertos TCP conocidos de NI; si Modbus estuviera abierto, lee registros.
# Uso: python probe_cfp.py
# Resultado del 21-oct-2026: 21, 80, 3580 y 59110 abiertos; 502 (Modbus), 2343 y 6000 cerrados.
# (Copia de Y:\Downloads\BACKUP_cFP2026-10-21\probe_cfp.py)
import socket, subprocess, datetime

HOST = "192.168.114.8"
PUERTOS = {
    21: "FTP",
    80: "Web server LabVIEW RT",
    502: "Modbus TCP",
    2343: "NI-PSP / variables compartidas",
    3580: "NI Service Locator",
    6000: "Logos (NI)",
    59110: "NI System Web Server",
}

print("==", datetime.datetime.now(), "==")
print(subprocess.run(["ping", "-n", "2", HOST], capture_output=True, text=True).stdout)

abiertos = []
for p, nombre in PUERTOS.items():
    s = socket.socket(); s.settimeout(2)
    ok = s.connect_ex((HOST, p)) == 0
    s.close()
    print(f"Puerto {p:>5} {nombre:<32} {'ABIERTO' if ok else 'cerrado'}")
    if ok: abiertos.append(p)

if 80 in abiertos:
    try:
        import urllib.request
        r = urllib.request.urlopen(f"http://{HOST}/", timeout=5)
        print("\nHTTP /:", r.status, r.read(300))
    except Exception as e:
        print("\nHTTP error:", e)

if 502 in abiertos:
    try:
        from pymodbus.client import ModbusTcpClient
        c = ModbusTcpClient(HOST, port=502); c.connect()
        for nombre, f in [("holding", c.read_holding_registers), ("input", c.read_input_registers),
                          ("coils", c.read_coils), ("discrete", c.read_discrete_inputs)]:
            try:
                r = f(0, count=10)
                print(nombre, getattr(r, "registers", None) or getattr(r, "bits", r))
            except Exception as e:
                print(nombre, "error:", e)
        c.close()
    except ImportError:
        print("\nModbus abierto: instala pymodbus (pip install pymodbus) y vuelve a correr.")
