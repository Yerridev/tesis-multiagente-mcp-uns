"""Diagnostico de ordenes: muestra en vivo las ordenes (/cmd) y respuestas (/ack, /state) de los 4 modulos
en el broker Windows (127.0.0.1:1883). Si aparece la /cmd pero no el /ack, el conector no la proceso.
Si no aparece ni la /cmd, el backend no esta publicando en este broker."""
import json
import sys
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PUERTO = int(sys.argv[2]) if len(sys.argv) > 2 else 1883
TOPICO = "uss/campus/lab-automatizacion/sl01la07/+/control/#"


def on_connect(c, *_):
    print(f"Conectado a {BROKER}:{PUERTO} · escuchando {TOPICO}")
    print("Ahora envia una orden desde el SCADA (Iniciar / Setpoint) y mira aqui...\n")
    c.subscribe(TOPICO, qos=1)


def on_message(c, u, m):
    modulo = m.topic.split("/")[4]
    tipo = m.topic.rsplit("/", 1)[-1].upper()
    try:
        d = json.loads(m.payload.decode("utf-8") or "{}")
        txt = " ".join(f"{k}={v}" for k, v in d.items() if k in ("tipo", "valor", "estado", "motivo", "modo", "plc", "id"))
    except ValueError:
        txt = m.payload.decode("utf-8", "replace")
    print(f"[{datetime.now():%H:%M:%S}] {modulo:<18} {tipo:<6} {txt}", flush=True)


cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="diag-ordenes")
cl.on_connect = on_connect
cl.on_message = on_message
cl.connect(BROKER, PUERTO, 30)
cl.loop_forever()
