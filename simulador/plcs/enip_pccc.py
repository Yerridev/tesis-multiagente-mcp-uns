"""Servidor EtherNet/IP + PCCC minimo (asyncio, sin dependencias) compatible con pycomm3.SLCDriver.

Implementa lo que usa SLCDriver contra un MicroLogix/SLC:
  encapsulacion: RegisterSession 0x65, UnRegisterSession 0x66, ListIdentity 0x63,
                 SendRRData 0x6F (Forward Open 0x54 / Forward Close 0x4E), SendUnitData 0x70
  CIP Execute PCCC (0x4B, clase 0x67) con comando 0x0F:
     funcion 0xA2 lectura tipada protegida (3 campos)  y  0xAA / 0xAB escritura (0xAB = enmascarada)

Tablas de datos (palabras de 16 bits):
  archivos numerados {numero: list[int]} p.ej. N7, B3, F8 (float = 2 palabras), T4 (3 palabras/elemento)
  E/S: O (archivo 0) e I (archivo 1) indexadas por (elemento=ranura, sub=palabra)
"""
from __future__ import annotations

import asyncio
import os
import struct

TIPO_A_PALABRAS = {0x89: 1, 0x85: 1, 0x8A: 2, 0x86: 3, 0x87: 3, 0x82: 1, 0x83: 1, 0x8B: 1, 0x8C: 1, 0x84: 1, 0x8D: 41}


class TablaDatos:
    def __init__(self):
        self.archivos: dict[int, list[int]] = {}
        self.io: dict[tuple[int, int, int], int] = {}   # (archivo 0=O/1=I, ranura, palabra) -> valor
        self.al_escribir = None                          # callback(archivo, elemento) opcional

    def crear(self, numero: int, palabras: int):
        self.archivos[numero] = [0] * palabras

    # ---- acceso por palabras ----
    def _leer_palabras(self, archivo, tipo, elem, sub, n_palabras):
        if tipo in (0x82, 0x83, 0x8B, 0x8C):
            return [self.io.get((archivo, elem, sub + i), 0) for i in range(n_palabras)]
        datos = self.archivos.get(archivo)
        if datos is None:
            raise KeyError
        base = elem * TIPO_A_PALABRAS.get(tipo, 1) + (sub if tipo in (0x86, 0x87) else 0)
        if base + n_palabras > len(datos):
            raise KeyError
        return datos[base:base + n_palabras]

    def _escribir_palabras(self, archivo, tipo, elem, sub, valores):
        if tipo in (0x82, 0x83, 0x8B, 0x8C):
            for i, v in enumerate(valores):
                self.io[(archivo, elem, sub + i)] = v
            return
        datos = self.archivos.get(archivo)
        if datos is None:
            raise KeyError
        base = elem * TIPO_A_PALABRAS.get(tipo, 1) + (sub if tipo in (0x86, 0x87) else 0)
        if base + len(valores) > len(datos):
            raise KeyError
        datos[base:base + len(valores)] = valores
        if self.al_escribir:
            self.al_escribir(archivo, elem)

    # ---- helpers para la logica del PLC ----
    def palabra(self, archivo, i) -> int:
        v = self.archivos[archivo][i]
        return v - 0x10000 if v >= 0x8000 else v

    def poner(self, archivo, i, v: int):
        self.archivos[archivo][i] = int(v) & 0xFFFF

    def bit(self, archivo, n) -> bool:
        return bool((self.archivos[archivo][n // 16] >> (n % 16)) & 1)

    def poner_bit(self, archivo, n, v: bool):
        w = self.archivos[archivo][n // 16]
        self.archivos[archivo][n // 16] = (w | (1 << (n % 16))) if v else (w & ~(1 << (n % 16)))

    def real(self, archivo, i) -> float:
        a = self.archivos[archivo]
        return struct.unpack("<f", struct.pack("<HH", a[2 * i], a[2 * i + 1]))[0]

    def poner_real(self, archivo, i, v: float):
        lo, hi = struct.unpack("<HH", struct.pack("<f", float(v)))
        self.archivos[archivo][2 * i:2 * i + 2] = [lo, hi]

    def io_bit(self, archivo, ranura, n) -> bool:
        return bool((self.io.get((archivo, ranura, 0), 0) >> n) & 1)

    def poner_io_bit(self, archivo, ranura, n, v: bool):
        w = self.io.get((archivo, ranura, 0), 0)
        self.io[(archivo, ranura, 0)] = (w | (1 << n)) if v else (w & ~(1 << n))

    def poner_io(self, archivo, ranura, palabra, v: int):
        self.io[(archivo, ranura, palabra)] = int(v) & 0xFFFF


class ServidorENIP:
    def __init__(self, tabla: TablaDatos, host="127.0.0.1", port=44818):
        self.tabla, self.host, self.port = tabla, host, port
        self.server = None
        self.conectado = True
        self._clientes: set[asyncio.StreamWriter] = set()

    async def iniciar(self):
        self.server = await asyncio.start_server(self._cliente, self.host, self.port)

    async def desconectar(self, caido: bool):
        """Simula el PLC caido: cierra el socket de escucha y corta a los clientes."""
        if caido and self.conectado:
            self.conectado = False
            self.server.close()
            for w in list(self._clientes):
                w.close()
        elif not caido and not self.conectado:
            await self.iniciar()
            self.conectado = True

    async def _cliente(self, reader, writer):
        self._clientes.add(writer)
        sesion = 0
        try:
            while True:
                cab = await reader.readexactly(24)
                cmd, largo, ses, _st = struct.unpack_from("<HHII", cab)
                contexto = cab[12:20]
                datos = await reader.readexactly(largo) if largo else b""
                if cmd == 0x65:                                   # RegisterSession
                    sesion = struct.unpack("<I", os.urandom(4))[0] or 1
                    resp = datos[:4] if len(datos) >= 4 else b"\x01\x00\x00\x00"
                elif cmd == 0x66:                                 # UnRegisterSession
                    break
                elif cmd == 0x63:                                 # ListIdentity
                    resp = self._list_identity()
                elif cmd == 0x6F:                                 # SendRRData (no conectado)
                    resp = self._send_rr(datos)
                elif cmd == 0x70:                                 # SendUnitData (conectado)
                    resp = self._send_unit(datos)
                else:
                    resp = b""
                out = struct.pack("<HHII", cmd, len(resp), sesion, 0) + contexto + b"\x00\x00\x00\x00" + resp
                writer.write(out)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            self._clientes.discard(writer)
            writer.close()

    @staticmethod
    def _cpf(items: list[tuple[int, bytes]]) -> bytes:
        b = b"\x00\x00\x00\x00" + b"\x0a\x00" + struct.pack("<H", len(items))
        for tipo, d in items:
            b += struct.pack("<HH", tipo, len(d)) + d
        return b

    def _list_identity(self) -> bytes:
        nombre = b"1763-L16BWA B/14.00"
        ident = (struct.pack("<H", 1) + struct.pack(">HHI", 2, 44818, 0) + b"\x00" * 8
                 + struct.pack("<HHHBBHI", 1, 0x0E, 90, 14, 0, 0x0030, 0x12345678)
                 + bytes([len(nombre)]) + nombre + b"\x03")
        return struct.pack("<H", 1) + struct.pack("<HH", 0x0C, len(ident)) + ident

    def _send_rr(self, d: bytes) -> bytes:
        # handle(4) timeout(2) count(2) [null item 4] [data item tipo,largo] -> CIP
        off, n = 8, struct.unpack_from("<H", d, 6)[0]
        cip = b""
        for _ in range(n):
            tipo, largo = struct.unpack_from("<HH", d, off)
            if tipo == 0xB2:
                cip = d[off + 4: off + 4 + largo]
            off += 4 + largo
        servicio = cip[0]
        ruta = cip[1] * 2
        cuerpo = cip[2 + ruta:]
        if servicio == 0x54:          # Forward Open
            ot_cid = os.urandom(4)
            to_cid, csn, vid, vsn = cuerpo[6:10], cuerpo[10:12], cuerpo[12:14], cuerpo[14:18]
            rep = ot_cid + to_cid + csn + vid + vsn + cuerpo[22:26] + cuerpo[28:32] + b"\x00\x00"
            reply = bytes([0xD4, 0, 0, 0]) + rep
        elif servicio == 0x4E:        # Forward Close
            reply = bytes([0xCE, 0, 0, 0]) + cuerpo[2:12] + b"\x00\x00"
        elif servicio == 0x4B:        # Execute PCCC no conectado
            reply = self._pccc(cuerpo)
        else:
            reply = bytes([servicio | 0x80, 0, 0x08, 0])   # servicio no soportado
        return self._cpf([(0x00, b""), (0xB2, reply)])

    def _send_unit(self, d: bytes) -> bytes:
        off, n = 8, struct.unpack_from("<H", d, 6)[0]
        cid, cip = b"\x00" * 4, b""
        for _ in range(n):
            tipo, largo = struct.unpack_from("<HH", d, off)
            if tipo == 0xA1:
                cid = d[off + 4: off + 8]
            elif tipo == 0xB1:
                cip = d[off + 4: off + 4 + largo]
            off += 4 + largo
        seq, cip = cip[:2], cip[2:]
        servicio = cip[0]
        cuerpo = cip[2 + cip[1] * 2:]
        reply = self._pccc(cuerpo) if servicio == 0x4B else bytes([servicio | 0x80, 0, 0x08, 0])
        return self._cpf([(0xA1, cid), (0xB1, seq + reply)])

    def _pccc(self, c: bytes) -> bytes:
        n_req = c[0]
        req_id = c[:n_req]                      # largo + vid + vsn (se devuelve igual)
        p = c[n_req:]
        cmd, _sts, tns, fnc = p[0], p[1], p[2:4], p[4]
        sts, datos = 0x00, b""
        try:
            if cmd == 0x0F and fnc == 0xA2:
                nbytes, archivo, tipo, elem, sub = p[5], p[6], p[7], p[8], p[9]
                pal = self.tabla._leer_palabras(archivo, tipo, elem, sub, max(1, (nbytes + 1) // 2))
                datos = b"".join(struct.pack("<H", w & 0xFFFF) for w in pal)[:nbytes]
            elif cmd == 0x0F and fnc in (0xAA, 0xAB):
                nbytes, archivo, tipo, elem, sub = p[5], p[6], p[7], p[8], p[9]
                carga = p[10:]
                if fnc == 0xAB:
                    mascara, carga = struct.unpack_from("<H", carga)[0], carga[2:]
                    if mascara == 0xFFFF:
                        pal = [struct.unpack_from("<H", carga, i)[0] for i in range(0, len(carga) - 1, 2)]
                        self.tabla._escribir_palabras(archivo, tipo, elem, sub, pal)
                    else:                       # escritura de bits enmascarada (una palabra)
                        actual = self.tabla._leer_palabras(archivo, tipo, elem, sub, 1)[0]
                        valor = struct.unpack_from("<H", carga)[0]
                        nuevo = (actual & ~mascara) | (valor & mascara)
                        self.tabla._escribir_palabras(archivo, tipo, elem, sub, [nuevo])
                else:
                    pal = [struct.unpack_from("<H", carga, i)[0] for i in range(0, len(carga) - 1, 2)]
                    self.tabla._escribir_palabras(archivo, tipo, elem, sub, pal)
            elif cmd == 0x06 and fnc == 0x03:   # diagnostic status (get_processor_type)
                datos = b"\x00" * 5 + b"1763-L16BWA\x00\x00\x00\x00\x00" + b"\x00" * 8
            else:
                sts = 0x10                      # comando ilegal
        except (KeyError, IndexError, struct.error):
            sts = 0x50                          # direccion no existe
        return bytes([0xCB, 0, 0, 0]) + req_id + bytes([cmd | 0x40, sts]) + tns + datos
