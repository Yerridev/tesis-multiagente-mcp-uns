"""Canal de difusión Server-Sent Events (SSE).

Sustituye al hub SignalR del backend ASP.NET.  El hub original era **solo de
push** (el navegador nunca invocaba métodos del servidor), así que SSE cubre
exactamente el mismo caso de uso con menos piezas:

* el navegador abre ``GET /api/stream`` con ``EventSource``;
* el servidor empuja eventos ``telemetry``, ``nivelSenales``, ... cada segundo;
* ``EventSource`` reconecta solo si se cae la conexión.

Formato SSE (RFC 8297)::

    event: telemetry
    data: [{...}]

    : ping
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from enum import Enum
from typing import Any, AsyncIterator

log = logging.getLogger(__name__)

#: Tamaño de la cola por cliente.  Si el navegador va lento se descartan los
#: mensajes más antiguos: la telemetría es un "último valor" y perder el
#: historial intermedio no aporta nada (el histórico real está en /api/history).
COLA_MAXIMO = 64

#: Cada cuánto se manda un comentario para que proxies y navegadores no
#: cierren la conexión por inactividad.
PING_SEGUNDOS = 15.0


def _json_default(valor: Any) -> str:
    """Serializa fechas y enums sin romper el JSON (ISO-8601 con offset)."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    return str(valor)


class CanalSSE:
    """Difusor de eventos a todos los clientes conectados."""

    def __init__(self) -> None:
        self._colas: set[asyncio.Queue[tuple[str, str]]] = set()
        self._lock = asyncio.Lock()

    async def suscribir(self) -> asyncio.Queue[tuple[str, str]]:
        cola: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=COLA_MAXIMO)
        async with self._lock:
            self._colas.add(cola)
        return cola

    async def desuscribir(self, cola: asyncio.Queue[tuple[str, str]]) -> None:
        async with self._lock:
            self._colas.discard(cola)

    @property
    def clientes(self) -> int:
        return len(self._colas)

    async def emitir(self, evento: str, datos: Any) -> None:
        """Publica un evento a todos los clientes suscritos."""
        try:
            cuerpo = json.dumps(datos, ensure_ascii=False, default=_json_default)
        except (TypeError, ValueError):                       # pragma: no cover
            cuerpo = json.dumps({"error": "NO_SERIALIZABLE"})
        async with self._lock:
            colas = list(self._colas)
        for cola in colas:
            try:
                cola.put_nowait((evento, cuerpo))
            except asyncio.QueueFull:
                # Cliente lento: se descarta el mensaje más viejo (la telemetría
                # es "último valor"; el histórico real no pasa por aquí).
                try:
                    cola.get_nowait()
                    cola.put_nowait((evento, cuerpo))
                except (asyncio.QueueEmpty, asyncio.QueueFull):  # pragma: no cover
                    pass


def _formatear(evento: str, cuerpo: str) -> bytes:
    return f"event: {evento}\ndata: {cuerpo}\n\n".encode("utf-8")


async def generar_stream(cola: asyncio.Queue[tuple[str, str]]) -> AsyncIterator[bytes]:
    """Generador de la respuesta SSE: emite lo que llega y pinguea si hay calma."""
    # Comentario inicial: el navegador abre la conexión y dispara 'onopen' ya.
    yield b": mcp-industrial stream abierto\n\n"
    try:
        while True:
            try:
                evento, cuerpo = await asyncio.wait_for(cola.get(), timeout=PING_SEGUNDOS)
            except asyncio.TimeoutError:
                yield b": ping\n\n"
                continue
            yield _formatear(evento, cuerpo)
    except asyncio.CancelledError:            # pragma: no cover - el navegador cortó
        raise
    except Exception:                          # pragma: no cover
        log.exception("Fallo el generador del stream SSE")
        raise
