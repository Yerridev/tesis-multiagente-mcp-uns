# Prueba 2 en la VM (SOLO LECTURA): DataSocket y servidor OPC FieldPoint.
# Uso:  python probe_ni_vm2.py > probe_ni_vm2.txt
import time

URLS = [
    "psp://192.168.114.8/FP/3AIO/00",
    "fieldpoint://192.168.114.8/FP/3AIO/00",
    "psp://192.168.114.8/DATOS_PAC/TRANS_PRESION",
    "psp://192.168.114.8/DATOS_PAC/SEL_MANUAL",
    "psp://192.168.114.8/pid/Kp_PC",
]
CWDS_READ_AUTOUPDATE = 2   # modos DataSocket: 1=Read, 2=ReadAutoUpdate (solo lectura)

print("=== A) DataSocket CWDSLib.CWDataSocket ===")
try:
    import win32com.client
    for u in URLS:
        try:
            ds = win32com.client.Dispatch("CWDSLib.CWDataSocket")
            ds.ConnectTo(u, CWDS_READ_AUTOUPDATE)
            v = None
            for _ in range(10):          # espera hasta 5 s a que llegue el primer valor
                time.sleep(0.5)
                try:
                    v = ds.Data.Value
                except Exception:
                    v = None
                if v is not None:
                    break
            try:
                estado = ds.Status
            except Exception:
                estado = "?"
            print("  {:<48} -> {!r}   (status={})".format(u, v, estado))
            ds.Disconnect()
        except Exception as e:
            print("  {:<48} ERROR: {}".format(u, e))
except ImportError:
    print("  falta pywin32")

print("\n=== B) Servidor OPC National Instruments.OPCFieldPoint (requiere OpenOPC) ===")
try:
    import OpenOPC
except ImportError:
    print("  OpenOPC no instalado. Si la parte A funciona, no hace falta.")
    print("  (Para instalarlo: pip install OpenOPC-Python3x  y registrar gbda_aut.dll con regsvr32)")
else:
    try:
        opc = OpenOPC.client()
        print("  Servidores:", opc.servers())
        opc.connect("National Instruments.OPCFieldPoint")
        items = opc.list("*", recursive=True, flat=True)
        print("  {} items. Primeros 60:".format(len(items)))
        for it in items[:60]:
            print("   ", it)
        if items:
            print("\n  Lectura de los 15 primeros:")
            for nombre, valor, calidad, ts in opc.read(items[:15], timeout=5000):
                print("   ", nombre, "=", valor, calidad, ts)
        opc.close()
    except Exception as e:
        print("  ERROR OPC:", e)
