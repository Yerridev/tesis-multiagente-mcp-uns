"""Publicación MQTT (órdenes de control y llaves del simulador).

El backend NUNCA escribe al PLC: solo publica la orden en el tópico ``cmd`` y
es el conector Python quien la ejecuta contra su propia allowlist.
"""

from __future__ import annotations

import asyncio
import logging
import threading

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)

_lock = threading.Lock()
_clientes: dict[tuple[str, int], mqtt.Client] = {}


def _crear(host: str, puerto: int) -> mqtt.Client:
    cliente = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"mcp-industrial-pub-{abs(hash((host, puerto))) % 10_000_000}",
    )
    cliente.reconnect_delay_set(1, 10)
    cliente.connect(host, puerto, keepalive=30)
    cliente.loop_start()
    return cliente


async def publicar(topico: str, cuerpo: str, host: str, puerto: int = 1883,
                   qos: int = 1, timeout: float = 3.0) -> bool:
    """Publica un mensaje. Devuelve ``False`` si el broker no está disponible."""
    clave = (host, puerto)
    with _lock:
        cliente = _clientes.get(clave)

    def _intento() -> bool:
        nonlocal cliente
        if cliente is None:
            cliente = _crear(host, puerto)
            with _lock:
                _clientes[clave] = cliente
        if not cliente.is_connected():
            try:
                cliente.reconnect()
            except OSError:
                return False
        info = cliente.publish(topico, cuerpo, qos=qos)
        info.wait_for_publish(timeout=timeout)
        return info.is_published()

    try:
        return await asyncio.to_thread(_intento)
    except Exception as exc:
        log.warning("No se pudo publicar en %s (%s:%s): %s", topico, host, puerto, exc)
        with _lock:
            _clientes.pop(clave, None)
        return False


def cerrar_todo() -> None:
    """Cierra los clientes persistentes (apagado limpio)."""
    with _lock:
        for cliente in _clientes.values():
            try:
                cliente.loop_stop()
                cliente.disconnect()
            except Exception:                # pragma: no cover
                pass
        _clientes.clear()
