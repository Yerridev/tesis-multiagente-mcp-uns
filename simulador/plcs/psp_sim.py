"""Servidor de 'variables compartidas' para el cFP-2200 virtual (sustituto simple de NI-PSP/DataSocket).

Protocolo: una linea JSON por peticion y por respuesta (TCP, puerto 6341 por defecto)
  {"op": "get", "url": "DATOS_PAC/TRANS_PRESION"}        -> {"ok": true, "valor": 0.0061}
  {"op": "set", "url": "pid/setpoint_pc", "valor": 20}   -> {"ok": true}
  {"op": "list"}                                         -> {"ok": true, "urls": [...]}
Lo usa el shim simulador/psp_shim (win32com.client.Dispatch("CWDSLib.CWDataSocket") falso).
"""
from __future__ import annotations

import asyncio
import json


class ServidorPSP:
    def __init__(self, plc, host="127.0.0.1", port=6341):
        self.plc, self.host, self.port = plc, host, port
        self.server = None
        self.conectado = False
        self._clientes = set()

    async def iniciar(self):
        self.server = await asyncio.start_server(self._cliente, self.host, self.port)
        self.conectado = True

    async def desconectar(self, caido: bool):
        if caido and self.conectado:
            self.conectado = False
            self.server.close()
            for w in list(self._clientes):
                w.close()
        elif not caido and not self.conectado:
            await self.iniciar()

    async def _cliente(self, reader, writer):
        self._clientes.add(writer)
        try:
            while line := await reader.readline():
                try:
                    r = json.loads(line)
                    op, url = r.get("op"), r.get("url")
                    if op == "get":
                        resp = {"ok": url in self.plc.vars, "valor": self.plc.vars.get(url)}
                    elif op == "set":
                        resp = {"ok": self.plc.escribir(url, r.get("valor"))}
                    elif op == "list":
                        resp = {"ok": True, "urls": sorted(self.plc.vars)}
                    else:
                        resp = {"ok": False}
                except Exception as ex:  # noqa: BLE001
                    resp = {"ok": False, "error": str(ex)}
                writer.write((json.dumps(resp) + "\n").encode())
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            self._clientes.discard(writer)
            writer.close()
