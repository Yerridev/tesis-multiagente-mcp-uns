"""Suscripción MQTT en asyncio.

El backend C# usaba ``MQTTnet`` con un ``BackgroundService`` por módulo.  Aquí
se usa ``paho-mqtt`` (el mismo cliente que ya usan los conectores edge y los
agentes), con la conexión en su propio hilo y los mensajes pasados al bucle
de asyncio con ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)

#: Segundos entre reintentos de conexión.
REINTENTO_S = 3.0


def _invocar(callback: Callable | None, *args) -> None:
    if callback is None:
        return
    try:
        callback(*args)
    except Exception:                       # pragma: no cover
        log.exception("Fallo un callback de MQTT")


async def consumir_topico(
    ctx,
    topico: str,
    al_mensaje: Callable[[str, str], None],
    cliente_id: str,
    al_conectar: Callable[[], None] | None = None,
    al_desconectar: Callable[[], None] | None = None,
    host: str | None = None,
    puerto: int | None = None,
    qos: int = 1,
) -> None:
    """Mantiene viva la suscripción a ``topico``; reconecta sola si se cae."""
    host = host or ctx.cfg.mqtt.host
    puerto = puerto or ctx.cfg.mqtt.port
    loop = asyncio.get_running_loop()

    while True:
        desconectado = threading.Event()
        cliente: mqtt.Client | None = None

        def _on_connect(cli, _userdata, _flags, reason_code, _properties=None):
            if getattr(reason_code, "is_failure", False):
                log.warning("MQTT rechazó la conexión a %s:%s (%s)", host, puerto, reason_code)
                desconectado.set()
                return
            cli.subscribe(topico, qos=qos)
            log.info("MQTT suscrito a %s (%s:%s)", topico, host, puerto)
            loop.call_soon_threadsafe(_invocar, al_conectar)

        def _on_disconnect(_cli, _userdata, _flags=None, _reason_code=None, _properties=None):
            loop.call_soon_threadsafe(_invocar, al_desconectar)
            desconectado.set()

        def _on_message(_cli, _userdata, mensaje):
            cuerpo = mensaje.payload.decode("utf-8", errors="replace")
            loop.call_soon_threadsafe(_invocar, al_mensaje, mensaje.topic, cuerpo)

        try:
            cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cliente_id)
            cliente.reconnect_delay_set(1, 10)
            cliente.on_connect = _on_connect
            cliente.on_disconnect = _on_disconnect
            cliente.on_message = _on_message
            cliente.connect(host, puerto, keepalive=30)
            cliente.loop_start()
            await asyncio.to_thread(desconectado.wait)
        except asyncio.CancelledError:
            raise
        except OSError as exc:
            log.warning("MQTT no disponible (%s:%s) — %s; reintento en %.0f s",
                        host, puerto, exc, REINTENTO_S)
            await asyncio.sleep(REINTENTO_S)
            continue
        except Exception:                    # pragma: no cover
            log.exception("Fallo la suscripción MQTT a %s", topico)
            await asyncio.sleep(REINTENTO_S)
            continue
        finally:
            if cliente is not None:
                try:
                    cliente.loop_stop()
                    cliente.disconnect()
                except Exception:            # pragma: no cover
                    pass

        log.info("MQTT desconectado de %s (%s); reintento en %.0f s", topico, host, REINTENTO_S)
        await asyncio.sleep(REINTENTO_S)
