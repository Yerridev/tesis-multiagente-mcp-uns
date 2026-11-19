"""Medidor de latencia PLC → backend (indicador VD-03).

Para cada dato que llega por MQTT se resta la hora en que el conector LEYÓ el
PLC (campo ``timestamp`` del mensaje) a la hora en que el backend lo RECIBE.
El conector y el backend corren en la misma PC (mismo reloj).

Se descartan los mensajes retenidos/viejos (> 60 s), que no son lecturas nuevas.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from datetime import datetime
from typing import Any

MAX_MUESTRAS = 2000

_lock = threading.Lock()
_por_modulo: dict[str, deque] = {}
_descartadas: dict[str, int] = {}
_desde = datetime.now().astimezone()


def registrar(modulo: str, senal: str, leido: datetime | None) -> None:
    if leido is None:
        return
    ahora = datetime.now().astimezone()
    ms = (ahora - leido).total_seconds() * 1000.0
    if ms > 60_000 or ms < -5_000:
        with _lock:
            _descartadas[modulo] = _descartadas.get(modulo, 0) + 1
        return
    with _lock:
        cola = _por_modulo.setdefault(modulo, deque(maxlen=MAX_MUESTRAS))
        cola.append({"recibido": ahora, "senal": senal, "ms": round(ms, 1)})


def reiniciar() -> None:
    global _desde
    with _lock:
        _por_modulo.clear()
        _descartadas.clear()
    _desde = datetime.now().astimezone()


def _percentil(ordenados: list[float], p: float) -> float:
    if not ordenados:
        return 0.0
    indice = max(0, min(len(ordenados) - 1, math.ceil(p * len(ordenados)) - 1))
    return ordenados[indice]


def resumen(con_muestras: bool) -> dict[str, Any]:
    with _lock:
        modulos = {}
        for clave, cola in _por_modulo.items():
            muestras = list(cola)
            valores = sorted(m["ms"] for m in muestras)
            n = len(valores)
            media = sum(valores) / n if n else 0.0
            if n < 2:
                desviacion = 0.0
            else:
                desviacion = math.sqrt(sum((v - media) ** 2 for v in valores) / (n - 1))
            modulos[clave] = {
                "n": n,
                "mediaMs": round(media, 1),
                "deMs": round(desviacion, 1),
                "medianaMs": _percentil(valores, 0.5),
                "p95Ms": _percentil(valores, 0.95),
                "minMs": valores[0] if n else 0,
                "maxMs": valores[-1] if n else 0,
                "descartadas": _descartadas.get(clave, 0),
                "muestras": muestras if con_muestras else None,
            }
    return {
        "desde": _desde,
        "hasta": datetime.now().astimezone(),
        "modulos": modulos,
    }
