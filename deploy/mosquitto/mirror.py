#!/usr/bin/env python3
"""
Espejo MQTT (solo desarrollo/lab): suscribe el UNS del laboratorio en el broker
ORIGINAL (servicio Windows de la tesis, host.docker.internal:1883) y lo
re-publica en el broker del stack docker (mosquitto:1883).

Dirección única Windows → Docker: no puede crear bucles. Sin credenciales,
sin escrituras, solo copia de payloads del topic raíz indicado.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

ORIGEN_HOST = os.environ.get("ORIGEN_HOST", "host.docker.internal")
ORIGEN_PUERTO = int(os.environ.get("ORIGEN_PUERTO", "1883"))
DESTINO_HOST = os.environ.get("DESTINO_HOST", "mosquitto")
DESTINO_PUERTO = int(os.environ.get("DESTINO_PUERTO", "1883"))
TOPICO = os.environ.get("TOPICO", "uss/campus/lab-automatizacion/sl01la07/#")


def log(evento: str, **c) -> None:
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "evento": evento, **c}), flush=True)


def main() -> None:
    dest = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mirror-tesis-docker")
    dest.connect(DESTINO_HOST, DESTINO_PUERTO, keepalive=30)
    dest.loop_start()
    log("destino_conectado", host=f"{DESTINO_HOST}:{DESTINO_PUERTO}")

    copiados = 0

    def on_connect(client, userdata, flags, reason_code, properties=None):
        client.subscribe(TOPICO, qos=1)
        log("origen_suscrito", topico=TOPICO)

    def on_message(client, userdata, msg):
        nonlocal copiados
        dest.publish(msg.topic, msg.payload, qos=1)
        copiados += 1
        if copiados % 100 == 0:
            log("progreso", copiados=copiados)

    origen = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="mirror-tesis-origen")
    origen.reconnect_delay_set(1, 30)
    origen.on_connect = on_connect
    origen.on_message = on_message

    while True:
        try:
            origen.connect(ORIGEN_HOST, ORIGEN_PUERTO, keepalive=30)
            origen.loop_start()
            while True:
                time.sleep(5)
        except Exception as ex:  # noqa: BLE001
            log("origen_reintento", error=str(ex))
            time.sleep(5)


if __name__ == "__main__":
    main()
