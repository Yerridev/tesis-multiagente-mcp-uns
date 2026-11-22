"""Shim de win32com.client: Dispatch("CWDSLib.CWDataSocket") falso que habla con simulador/plcs/psp_sim.py.

Uso (los conectores no cambian):
    set PYTHONPATH=<proyecto>\\simulador\\psp_shim          (Windows)
    export PYTHONPATH=<proyecto>/simulador/psp_shim         (Linux)
    python conectores/conector_edge_cfp2200.py --cfp 127.0.0.1 --broker 127.0.0.1
Puerto del simulador: variable de entorno PSP_SIM_PORT (por defecto 6341).
El host sale de la URL psp://<host>/<variable>, o sea del --cfp del conector.
"""
import json
import os
import socket
from urllib.parse import urlparse

STATUS_OK, STATUS_ERROR = 2, 3


class _Canal:
    def __init__(self, host, port):
        self.host, self.port, self.sock, self.f = host, port, None, None

    def pedir(self, msg):
        for _ in range(2):
            try:
                if self.sock is None:
                    self.sock = socket.create_connection((self.host, self.port), timeout=2)
                    self.f = self.sock.makefile("rwb")
                self.f.write((json.dumps(msg) + "\n").encode())
                self.f.flush()
                linea = self.f.readline()
                if not linea:
                    raise OSError("cerrado")
                return json.loads(linea)
            except OSError:
                self.cerrar()
        return None

    def cerrar(self):
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.sock = self.f = None


class _Data:
    def __init__(self, ds):
        object.__setattr__(self, "_ds", ds)

    @property
    def Value(self):
        return self._ds._get()

    def __setattr__(self, k, v):
        if k == "Value":
            self._ds._set(v)
        else:
            object.__setattr__(self, k, v)


class CWDataSocket:
    def __init__(self):
        self._canal, self._url, self._status = None, None, 0
        self.Data = _Data(self)

    def ConnectTo(self, url, modo=2):
        u = urlparse(url)
        self._url = u.path.lstrip("/")
        self._canal = _Canal(u.hostname, int(os.environ.get("PSP_SIM_PORT", "6341")))
        self._status = STATUS_OK if self._canal.pedir({"op": "get", "url": self._url}) else STATUS_ERROR

    @property
    def Status(self):
        if self._canal is None:
            return 0
        r = self._canal.pedir({"op": "get", "url": self._url})
        self._status = STATUS_OK if (r and r.get("ok")) else STATUS_ERROR
        return self._status

    def _get(self):
        r = self._canal.pedir({"op": "get", "url": self._url}) if self._canal else None
        return r.get("valor") if r and r.get("ok") else None

    def _set(self, v):
        r = self._canal.pedir({"op": "set", "url": self._url, "valor": v}) if self._canal else None
        if not (r and r.get("ok")):
            raise RuntimeError("escritura rechazada por el cFP virtual: " + str(self._url))

    def Update(self):
        pass

    def Disconnect(self):
        if self._canal:
            self._canal.cerrar()
        self._status = 0


def Dispatch(progid):
    if progid.startswith("CWDSLib.CWDataSocket"):
        return CWDataSocket()
    raise RuntimeError("shim del simulador: ProgID no soportado: " + progid)
