"""Servidor Modbus TCP minimo (sin dependencias) para emular PLC.

Funciones soportadas: FC01 leer coils, FC02 leer entradas discretas (= coils),
FC03/FC04 leer registros, FC05 escribir coil, FC06 escribir registro,
FC15 escribir coils, FC16 escribir registros.
Responde a cualquier unit id (el Twido real acepta 1 y 255).
Direcciones en base 0, igual que el Twido: %Mi = coil i, %MWi = holding register i.
"""
from __future__ import annotations

import asyncio
import struct
from typing import Callable

MAX_BITS, MAX_REGS = 2000, 125


class Memoria:
    """Memoria del PLC: coils (%M) y registros (%MW)."""

    def __init__(self, n_coils: int = 256, n_regs: int = 256):
        self.coils = [False] * n_coils
        self.regs = [0] * n_regs
        # Se llama tras cada escritura externa: (tipo 'M'|'MW', direccion, valores)
        self.al_escribir: Callable[[str, int, list], None] | None = None


class ServidorModbus:
    def __init__(self, mem: Memoria, host: str = "0.0.0.0", port: int = 502):
        self.mem, self.host, self.port = mem, host, port
        self.conectado = True          # False = simula PLC caido (no responde)
        self._server: asyncio.base_events.Server | None = None
        self._clientes: set[asyncio.StreamWriter] = set()
        self.peticiones = 0

    async def iniciar(self):
        self._server = await asyncio.start_server(self._atender, self.host, self.port)

    def desconectar(self, valor: bool):
        """Simula PLC caido: cierra conexiones y deja de responder."""
        self.conectado = not valor
        if valor:
            for w in list(self._clientes):
                w.close()

    async def _atender(self, r: asyncio.StreamReader, w: asyncio.StreamWriter):
        if not self.conectado:
            w.close()
            return
        self._clientes.add(w)
        try:
            while self.conectado:
                cab = await r.readexactly(7)
                tid, pid, largo, unit = struct.unpack(">HHHB", cab)
                pdu = await r.readexactly(largo - 1)
                resp = self._procesar(pdu)
                w.write(struct.pack(">HHHB", tid, pid, len(resp) + 1, unit) + resp)
                await w.drain()
                self.peticiones += 1
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            self._clientes.discard(w)
            w.close()

    @staticmethod
    def _error(fc: int, codigo: int) -> bytes:
        return bytes([fc | 0x80, codigo])

    def _procesar(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        m = self.mem
        try:
            if fc in (1, 2):
                dir_, n = struct.unpack(">HH", pdu[1:5])
                if not 1 <= n <= MAX_BITS or dir_ + n > len(m.coils):
                    return self._error(fc, 2)
                bits = m.coils[dir_:dir_ + n]
                datos = bytearray((n + 7) // 8)
                for i, b in enumerate(bits):
                    if b:
                        datos[i // 8] |= 1 << (i % 8)
                return bytes([fc, len(datos)]) + bytes(datos)
            if fc in (3, 4):
                dir_, n = struct.unpack(">HH", pdu[1:5])
                if not 1 <= n <= MAX_REGS or dir_ + n > len(m.regs):
                    return self._error(fc, 2)
                vals = [v & 0xFFFF for v in m.regs[dir_:dir_ + n]]
                return bytes([fc, 2 * n]) + struct.pack(f">{n}H", *vals)
            if fc == 5:
                dir_, v = struct.unpack(">HH", pdu[1:5])
                if dir_ >= len(m.coils) or v not in (0x0000, 0xFF00):
                    return self._error(fc, 3 if v not in (0, 0xFF00) else 2)
                m.coils[dir_] = v == 0xFF00
                self._aviso("M", dir_, [m.coils[dir_]])
                return pdu[:5]
            if fc == 6:
                dir_, v = struct.unpack(">HH", pdu[1:5])
                if dir_ >= len(m.regs):
                    return self._error(fc, 2)
                m.regs[dir_] = v
                self._aviso("MW", dir_, [v])
                return pdu[:5]
            if fc == 15:
                dir_, n, nb = struct.unpack(">HHB", pdu[1:6])
                if dir_ + n > len(m.coils):
                    return self._error(fc, 2)
                datos = pdu[6:6 + nb]
                vals = [bool(datos[i // 8] >> (i % 8) & 1) for i in range(n)]
                m.coils[dir_:dir_ + n] = vals
                self._aviso("M", dir_, vals)
                return pdu[:5]
            if fc == 16:
                dir_, n, nb = struct.unpack(">HHB", pdu[1:6])
                if dir_ + n > len(m.regs):
                    return self._error(fc, 2)
                vals = list(struct.unpack(f">{n}H", pdu[6:6 + nb]))
                m.regs[dir_:dir_ + n] = vals
                self._aviso("MW", dir_, vals)
                return pdu[:5]
            return self._error(fc, 1)
        except struct.error:
            return self._error(fc, 3)

    def _aviso(self, tipo, dir_, vals):
        if self.mem.al_escribir:
            self.mem.al_escribir(tipo, dir_, vals)
