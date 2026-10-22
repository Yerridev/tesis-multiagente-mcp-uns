# Diagnostico SOLO LECTURA del cFP-2200 por FTP (no escribe ni borra nada en el equipo)
# Descarga el listado completo del disco y los archivos de texto (.ini, .txt, .log, ...)
# a una carpeta DIAG_cFP_<fecha> junto a la carpeta del script.
# Uso:  python diag_cfp.py
# (Copia de Y:\Downloads\BACKUP_cFP2026-10-21\diag_cfp.py, usada el 21-oct-2026)
import ftplib, os, datetime

HOST = "192.168.114.8"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "DIAG_cFP_" + datetime.datetime.now().strftime("%Y%m%d_%H%M"))
OUT = os.path.abspath(OUT)
TEXT_EXT = (".ini", ".txt", ".log", ".conf", ".aliases", ".cfg", ".xml")
os.makedirs(OUT, exist_ok=True)
listing = open(os.path.join(OUT, "listado_completo.txt"), "w", encoding="utf-8")

ftp = ftplib.FTP(HOST, timeout=20)
ftp.login()
listing.write("WELCOME: %s\n\n" % ftp.getwelcome())

def is_dir(path):
    cur = ftp.pwd()
    try:
        ftp.cwd(path); ftp.cwd(cur); return True
    except ftplib.all_errors:
        try: ftp.cwd(cur)
        except ftplib.all_errors: pass
        return False

def walk(path, depth=0):
    if depth > 6: return
    lines = []
    try: ftp.retrlines("LIST " + path, lines.append)
    except ftplib.all_errors as e:
        listing.write("[ERROR LIST %s] %s\n" % (path, e)); return
    listing.write("\n=== %s ===\n" % path)
    for l in lines: listing.write(l + "\n")
    try: names = ftp.nlst(path)
    except ftplib.all_errors: names = []
    for n in names:
        base = n.rstrip("/").split("/")[-1]
        if base in (".", ".."): continue
        full = n if n.startswith("/") else (path.rstrip("/") + "/" + base)
        if is_dir(full):
            if base.lower() in ("errors", "www", "webserver", "vxipnp"): continue
            walk(full, depth + 1)
        elif base.lower().endswith(TEXT_EXT):
            local = os.path.join(OUT, full.strip("/").replace("/", "__"))
            try:
                with open(local, "wb") as fh: ftp.retrbinary("RETR " + full, fh.write)
            except ftplib.all_errors as e:
                listing.write("[ERROR RETR %s] %s\n" % (full, e))

walk("/")
ftp.quit(); listing.close()
print("Listo. Resultados en:", OUT)
