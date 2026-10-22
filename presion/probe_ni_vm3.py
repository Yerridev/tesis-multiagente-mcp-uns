# Prueba 3 en la VM (SOLO LECTURA): DataSocket bombeando mensajes COM + OPC FieldPoint.
# Uso:  python probe_ni_vm3.py > probe_ni_vm3.txt
import time
import pythoncom
import win32com.client

URLS = [
    "psp://192.168.114.8/FP/3AIO/00",
    "fieldpoint://192.168.114.8/FP/3AIO/00",
    "psp://192.168.114.8/DATOS_PAC/TRANS_PRESION",
    "psp://192.168.114.8/DATOS_PAC/SEL_MANUAL",
    "psp://192.168.114.8/pid/Kp_PC",
]

print("=== A) DataSocket con bombeo de mensajes ===")
conexiones = []
for u in URLS:
    try:
        ds = win32com.client.Dispatch("CWDSLib.CWDataSocket")
        ds.ConnectTo(u, 2)              # 2 = ReadAutoUpdate (solo lectura)
        conexiones.append((u, ds))
    except Exception as e:
        print("  {:<48} ERROR al conectar: {}".format(u, e))

fin = time.time() + 8                   # 8 s procesando eventos COM
while time.time() < fin:
    pythoncom.PumpWaitingMessages()
    time.sleep(0.05)

for u, ds in conexiones:
    for intento in ("Data.Value", "Update"):
        try:
            if intento == "Update":
                ds.Update()             # pide el valor actual al servidor (lectura)
                t = time.time() + 3
                while time.time() < t:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.05)
            v = ds.Data.Value
        except Exception as e:
            v = "ERROR {}".format(e)
        try:
            st = ds.Status
        except Exception:
            st = "?"
        try:
            err = ds.LastError
        except Exception:
            err = "-"
        print("  {:<48} [{}] -> {!r}  status={} lasterror={}".format(u, intento, v, st, err))
for u, ds in conexiones:
    try:
        ds.Disconnect()
    except Exception:
        pass

print("\n=== B) OPC National Instruments.OPCFieldPoint ===")
try:
    import OpenOPC
except ImportError:
    print("  OpenOPC no instalado.")
else:
    try:
        opc = OpenOPC.client()
        opc.connect("National Instruments.OPCFieldPoint")
        items = opc.list("*", recursive=True, flat=True)
        print("  {} items:".format(len(items)))
        for it in items[:80]:
            print("   ", it)
        for nombre, valor, calidad, ts in opc.read(items[:20], timeout=5000):
            print("   ", nombre, "=", valor, calidad, ts)
        opc.close()
    except Exception as e:
        print("  ERROR OPC:", e)
