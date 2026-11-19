"""Auditoría de control: JSONL append-only + búfer en memoria.

Port de ``Control/ControlAuditoria.cs``.  Cada orden deja rastro de quién la
expedió, con qué rol, en qué modo y con qué resultado.  Es la evidencia de la
tesis: el bypass del guard de calidad queda marcado aquí.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_RECIENTES = 500


class ControlAuditoria:
    def __init__(self, carpeta: str | None = None) -> None:
        self._lock = threading.Lock()
        self._recientes: deque[dict[str, Any]] = deque(maxlen=MAX_RECIENTES)
        self._ruta: Path | None = None
        if carpeta:
            destino = Path(carpeta)
        else:
            destino = Path(__file__).resolve().parents[2] / "auditoria"
        try:
            destino.mkdir(parents=True, exist_ok=True)
            self._ruta = destino / f"control-{datetime.now().astimezone():%Y%m%d}.jsonl"
        except OSError as exc:
            log.warning("Auditoría de control sin archivo (solo memoria): %s", exc)
            self._ruta = None

    def registrar(self, accion: str, orden_id: str | None, usuario: str, rol: str,
                  resultado: str, detalle: str | None) -> None:
        evento = {
            "ts": datetime.now().astimezone(),
            "accion": accion,
            "ordenId": orden_id,
            "usuario": usuario,
            "rol": rol,
            "resultado": resultado,
            "detalle": detalle,
        }
        with self._lock:
            self._recientes.append(evento)
        if self._ruta is None:
            return
        try:
            with self._ruta.open("a", encoding="utf-8") as archivo:
                archivo.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            log.warning("No se pudo escribir la auditoría de control: %s", exc)

    def ultimas(self, limite: int = 50) -> list[dict[str, Any]]:
        limite = max(1, min(MAX_RECIENTES, limite if limite and limite > 0 else 50))
        with self._lock:
            return list(reversed(self._recientes))[:limite]
