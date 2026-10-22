"""
Importa los historicos LabVIEW (.lvm) del SCADA original (Inducontrol, 2008-2011) a TimescaleDB.

Formato: 8 canales, 1 muestra por fila, tiempo relativo (X_Value) desde la fecha/hora del encabezado.
Separador decimal variable ('.' o ','), se lee del encabezado.

Mapa de canales (inferido de los datos; el SCADA los guardo como "Untitled..."):
  0 setpoint (L/min) | 1 caudal (L/min) | 2 salida variador (%) | 3 valvula (%)
  4 Kc | 5 Ti [min] | 6 Td [min] (antes etiquetados KP/KI/KD) | 7 indicador de modo (0/1, significado por confirmar)

Es idempotente: si un archivo se importa dos veces (o aparece duplicado en otra carpeta),
las filas repetidas se descartan por la restriccion UNIQUE (variable, fuente, time).

Modulo de NIVEL MCN-09 (--modulo nivel): mismo formato de 8 canales, variables con prefijo 'nivel-mcn09/':
  0 setpoint (cm) | 1 nivel T2 (cm) | 2 senal de control (%) | 3 valvula (%) | 4 Kc | 5 Ti | 6 Td | 7 modo (0/1/2)
  Evidencia: el canal 1 satura en ~42 cm igual que el sensor ultrasonico hoy (~40,7 cm) y la escala del HMI es 0-35 cm.

Uso:
    pip install "psycopg[binary]"
    python importar_lvm.py "Y:\\Downloads\\TODO-CAUDAL-PC-XP" --dsn postgresql://uns_admin:cambiar_esto@localhost:5432/uns
    python importar_lvm.py CARPETA_NIVEL --modulo nivel --dsn ...
    python importar_lvm.py CARPETA --solo-revisar        # no escribe; muestra lo que importaria
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ_LIMA = timezone(timedelta(hours=-5))
CANALES_CAUDAL = [
    ("caudal/setpoint", "L/min"),
    ("caudal/pv_pid", "L/min"),
    ("actuadores/variador_pct", "%"),
    ("actuadores/valvula_pct", "%"),
    ("pid/kc", None),          # el SCADA escribia VD100/VD108/VD116 -> el PLC los copia a Kc, Ti, Td (VD171/179/183)
    ("pid/ti", "min"),
    ("pid/td", "min"),
    ("estado/modo_lvm", None),
]
CANALES_NIVEL = [
    ("nivel-mcn09/pid/setpoint_cm", "cm"),
    ("nivel-mcn09/nivel/cm", "cm"),          # mismo nombre que el dato en vivo: comparable con fuente='lvm'
    ("nivel-mcn09/pid/senal_control_pct", "%"),
    ("nivel-mcn09/valvula/apertura_pct", "%"),
    ("nivel-mcn09/pid/kc", None),
    ("nivel-mcn09/pid/ti", None),
    ("nivel-mcn09/pid/td", None),
    ("nivel-mcn09/estado/modo_lvm", None),
]
MODULOS = {"caudal": CANALES_CAUDAL, "nivel": CANALES_NIVEL}
CANALES = CANALES_CAUDAL   # se reemplaza en main() segun --modulo


def num(texto: str, decimal: str) -> float:
    return float(texto.strip().replace(decimal, ".") if decimal != "." else texto.strip())


def leer_fecha(fecha: str):
    """Acepta 2008/02/04 (LabVIEW) y 29/12/2008 (archivo re-guardado con Excel)."""
    for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(fecha, fmt).date()
        except ValueError:
            pass
    return None


def hora_desde_nombre(stem: str, d, minuto: int, segundo: int):
    """El SCADA nombra los archivos AAAA M D H M S sin ceros (p. ej. 20081229151041 = 15:10:41).
    Busca la hora que reproduce exactamente el nombre del archivo."""
    for h in range(24):
        for f in ("{y}{mo}{d}{h}{mi}{s}", "{y}{mo:02d}{d:02d}{h:02d}{mi:02d}{s:02d}"):
            if f.format(y=d.year, mo=d.month, d=d.day, h=h, mi=minuto, s=segundo) == stem:
                return h
    return None


def calcular_inicio(fecha: str, hora: str, stem: str):
    """Devuelve (datetime inicial, aviso). Tolera hora 'HH:MM:SS.f' y la truncada 'MM:SS.f' de Excel."""
    d = leer_fecha(fecha)
    if d is None:
        return None, f"fecha no reconocida '{fecha}'"
    partes = hora.replace(",", ".").split(":")
    try:
        if len(partes) == 3:
            h, m, sec = int(partes[0]), int(partes[1]), float(partes[2])
        elif len(partes) == 2:
            m, sec = int(partes[0]), float(partes[1])
            h = hora_desde_nombre(stem, d, m, int(sec))
            if h is None:
                return None, f"hora incompleta '{hora}' y no se pudo deducir del nombre"
        else:
            return None, f"hora no reconocida '{hora}'"
    except ValueError:
        return None, f"hora no reconocida '{hora}'"
    base = datetime(d.year, d.month, d.day, h, m, tzinfo=TZ_LIMA)
    return base + timedelta(seconds=sec), None


def parsear_lvm(ruta: Path):
    """Devuelve (lista de filas (time, variable, valor, unidad, 'lvm', archivo), aviso o None)."""
    lineas = ruta.read_text(encoding="latin-1").splitlines()
    if not lineas or not lineas[0].startswith("LabVIEW Measurement"):
        return [], "no es un archivo LVM"
    decimal = "."
    fecha = hora = None
    fin_cabeceras = 0
    for i, l in enumerate(lineas):
        partes = l.split("\t")
        clave = partes[0].strip()
        if clave == "Decimal_Separator" and len(partes) > 1:
            decimal = partes[1].strip() or "."
        elif clave == "Date" and len(partes) > 1 and partes[1].strip():
            fecha = partes[1].strip()          # la ultima Date/Time (cabecera de canales) es la buena
        elif clave == "Time" and len(partes) > 1 and partes[1].strip():
            hora = partes[1].strip()
        elif clave == "X_Value":
            fin_cabeceras = i
            break
    if not fin_cabeceras or not fecha or not hora:
        return [], "cabecera incompleta"
    inicio, aviso = calcular_inicio(fecha, hora, ruta.stem)
    if inicio is None:
        return [], aviso

    filas = []
    for l in lineas[fin_cabeceras + 1:]:
        partes = l.split("\t")
        if len(partes) < 2 or not partes[0].strip():
            continue
        try:
            t = inicio + timedelta(seconds=num(partes[0], decimal))
            valores = [num(p, decimal) for p in partes[1:1 + len(CANALES)] if p.strip()]
        except ValueError:
            continue
        for (variable, unidad), v in zip(CANALES, valores):
            filas.append((t, variable, v, unidad, "lvm", ruta.name))
    return filas, None


def main():
    p = argparse.ArgumentParser(description="Importador de historicos .lvm a TimescaleDB")
    p.add_argument("carpeta", help="Carpeta raiz; se buscan .lvm en todas las subcarpetas")
    p.add_argument("--dsn", default="postgresql://uns_admin:cambiar_esto@localhost:5432/uns")
    p.add_argument("--solo-revisar", action="store_true", help="No escribe en la base")
    p.add_argument("--modulo", choices=sorted(MODULOS), default="caudal", help="Mapa de canales a usar")
    a = p.parse_args()
    global CANALES
    CANALES = MODULOS[a.modulo]
    print(f"Modulo: {a.modulo} -> {', '.join(v for v, _ in CANALES)}\n")

    archivos = sorted(Path(a.carpeta).rglob("*.lvm"))
    if not archivos:
        sys.exit(f"No se encontraron .lvm en {a.carpeta}")

    con = None
    if not a.solo_revisar:
        import psycopg
        con = psycopg.connect(a.dsn)

    total_filas = total_nuevas = omitidos = 0
    for ruta in archivos:
        try:
            filas, aviso = parsear_lvm(ruta)
        except Exception as e:  # un archivo raro no debe detener la importacion
            filas, aviso = [], f"error inesperado: {e}"
        if aviso:
            print(f"  OMITIDO  {ruta.name}: {aviso}")
            omitidos += 1
            continue
        nuevas = 0
        if con and filas:
            with con.cursor() as cur:
                cur.executemany(
                    """INSERT INTO mediciones (time, variable, valor, unidad, fuente, direccion)
                       VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""", filas)
                nuevas = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            con.commit()
        muestras = len(filas) // len(CANALES)
        rango = f"{filas[0][0]:%Y-%m-%d %H:%M} -> {filas[-1][0]:%H:%M}" if filas else "-"
        print(f"  {ruta.name:<28} {muestras:>6} muestras  {rango}")
        total_filas += len(filas)
        total_nuevas += nuevas

    print(f"\n{len(archivos)} archivos ({omitidos} omitidos), {total_filas} valores leidos"
          + ("" if a.solo_revisar else f", {total_nuevas} insertados (el resto ya existia)"))
    if con:
        con.close()


if __name__ == "__main__":
    main()
