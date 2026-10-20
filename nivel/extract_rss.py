"""
Extrae el contenido legible de un proyecto RSLogix 500 (.RSS) sin RSLogix.
El .RSS es un contenedor OLE con streams comprimidos en zlib.

Uso:
    pip install olefile
    python extract_rss.py "Y:\\Downloads\\upload final.RSS"

Salida (junto a este script):
    rss_dump.txt        -> resumen legible: streams, textos, simbolos, comentarios
    rss_streams\\       -> cada stream crudo y descomprimido (.bin)
Solo lee el .RSS; no lo modifica.
"""
import re
import sys
import zlib
from pathlib import Path

import olefile

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else r"Y:\Downloads\upload final.RSS")
OUT = Path(__file__).parent
STREAMS_DIR = OUT / "rss_streams"
STREAMS_DIR.mkdir(exist_ok=True)

ASCII_RE = re.compile(rb"[\x20-\x7E]{3,}")
UTF16_RE = re.compile(rb"(?:[\x20-\x7E]\x00){3,}")


def strings(data):
    found = [m.group().decode("ascii") for m in ASCII_RE.finditer(data)]
    found += [m.group().decode("utf-16le") for m in UTF16_RE.finditer(data)]
    return found


def inflate_all(data):
    """Descomprime cada bloque zlib que encuentre dentro del stream."""
    blocks = []
    for m in re.finditer(rb"\x78[\x01\x5e\x9c\xda]", data):
        try:
            d = zlib.decompressobj()
            out = d.decompress(data[m.start():])
            if len(out) > 4:
                blocks.append((m.start(), out))
        except zlib.error:
            pass
    return blocks


def main():
    ole = olefile.OleFileIO(str(SRC))
    lines = [f"ARCHIVO: {SRC}", ""]
    for entry in ole.listdir(streams=True, storages=False):
        name = "/".join(entry)
        raw = ole.openstream(entry).read()
        safe = re.sub(r"[^\w.-]+", "_", name)
        (STREAMS_DIR / f"{safe}.raw.bin").write_bytes(raw)

        lines.append("=" * 80)
        lines.append(f"STREAM: {name}   ({len(raw)} bytes)")
        s = strings(raw)
        if s:
            lines.append("  [texto crudo] " + " | ".join(s[:200]))

        for i, (off, dec) in enumerate(inflate_all(raw)):
            (STREAMS_DIR / f"{safe}.z{i}.bin").write_bytes(dec)
            ds = strings(dec)
            lines.append(f"  [zlib @ {off}: {len(dec)} bytes] " + " | ".join(ds[:400]))
    ole.close()

    dump = OUT / "rss_dump.txt"
    dump.write_text("\n".join(lines), encoding="utf-8")
    print(f"Listo: {dump}  ({len(lines)} lineas)  | streams en {STREAMS_DIR}")


if __name__ == "__main__":
    main()
