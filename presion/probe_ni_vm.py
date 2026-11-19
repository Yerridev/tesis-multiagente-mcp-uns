# Detecta en la VM Windows 7 que interfaces de NI quedaron instaladas (OPC, DataSocket, FieldPoint).
# SOLO LECTURA: revisa el registro de Windows y, si hay DataSocket, intenta LEER una variable del cFP.
# Uso (en la VM):  python probe_ni_vm.py > probe_ni_vm.txt
import sys

try:
    import winreg
except ImportError:
    import _winreg as winreg

CLAVES = ("datasocket", "fieldpoint", "opc", "national instruments", "cwds", "ni.", "nipsp", "variable")

print("Python:", sys.version)
print("\n=== ProgIDs relacionados con NI / OPC / DataSocket ===")
progids = []
i = 0
while True:
    try:
        k = winreg.EnumKey(winreg.HKEY_CLASSES_ROOT, i)
    except OSError:
        break
    i += 1
    kl = k.lower()
    if any(c in kl for c in CLAVES) and not kl.startswith("."):
        es_opc = False
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, k + "\\OPC"))
            es_opc = True
        except OSError:
            pass
        progids.append(k)
        print(("[SERVIDOR OPC] " if es_opc else "               ") + k)

print("\n=== Categoria OPC DA registrada (servidores OPC del equipo) ===")
CAT = "{63D5F432-CFE4-11D1-B2C8-0060083BA1FB}"  # OPC DA 2.0
try:
    clsid_root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "CLSID")
    n = 0
    j = 0
    while True:
        try:
            clsid = winreg.EnumKey(clsid_root, j)
        except OSError:
            break
        j += 1
        try:
            winreg.CloseKey(winreg.OpenKey(clsid_root, clsid + "\\Implemented Categories\\" + CAT))
            try:
                pk = winreg.OpenKey(clsid_root, clsid + "\\ProgID")
                pid = winreg.QueryValue(pk, None)
            except OSError:
                pid = "(sin ProgID)"
            print("  OPC DA:", pid, clsid)
            n += 1
        except OSError:
            pass
    if n == 0:
        print("  (ningun servidor OPC DA 2.0 registrado)")
except OSError as e:
    print("  error:", e)

print("\n=== Prueba de lectura via DataSocket (COM), solo lectura ===")
try:
    import win32com.client
except ImportError:
    print("  pywin32 no instalado (pip install pywin32). Se omite.")
else:
    candidatos = [p for p in progids if "datasocket" in p.lower() or "cwds" in p.lower()]
    urls = ["psp://192.168.114.8/FP/3AIO/00", "fieldpoint://192.168.114.8/FP/3AIO/00",
            "psp://192.168.114.8/DATOS_PAC/TRANS_PRESION"]
    for prog in candidatos:
        try:
            ds = win32com.client.Dispatch(prog)
        except Exception as e:
            print("  ", prog, "no instanciable:", e)
            continue
        print("  Objeto creado:", prog)
        for u in urls:
            try:
                ds.ConnectTo(u, 1)  # 1 = cwdsRead (solo lectura)
                import time
                time.sleep(2)
                v = ds.Data.Value
                print("    ", u, "->", v)
                ds.Disconnect()
            except Exception as e:
                print("    ", u, "error:", e)
        break
    if not candidatos:
        print("  No hay ProgID de DataSocket registrado.")
