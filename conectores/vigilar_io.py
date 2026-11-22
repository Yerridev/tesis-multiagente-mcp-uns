#!/usr/bin/env python3
"""Muestra EN VIVO los cambios de las entradas/salidas del S7-200 de caudal (solo lectura).
Uso: acciona algo en el tablero (guardamotor, paro de emergencia, pulsadores) y mira que bit cambia."""
import json, sys
from datetime import datetime
import paho.mqtt.client as mqtt

BASE = "uss/campus/lab-automatizacion/sl01la07/caudal-mcc09/funcional/"
VIGILAR = ("io/", "estado/")          # bits sin documentar + los ya conocidos
estado = {}

def al_conectar(c, u, *a):
    c.subscribe(BASE + "#", qos=1)
    print("Conectado al broker 127.0.0.1:1883. Esperando cambios... (Ctrl+C para salir)\n", flush=True)

def al_mensaje(c, u, m):
    clave = m.topic[len(BASE):]
    if not clave.startswith(VIGILAR): return
    try: v = json.loads(m.payload)["value"]
    except Exception: return
    if not isinstance(v, bool): return
    previo = estado.get(clave)
    estado[clave] = v
    hora = datetime.now().strftime("%H:%M:%S")
    if previo is None:
        if v: print(f"[{hora}] inicial   {clave:<28} = ON", flush=True)
    elif previo != v:
        print(f"[{hora}] >>> CAMBIO {clave:<28} {'OFF -> ON ' if v else 'ON  -> OFF'}  <<<", flush=True)

cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="vigilar-io-caudal")
cli.on_connect, cli.on_message = al_conectar, al_mensaje
cli.connect("127.0.0.1", 1883, 30)
try: cli.loop_forever()
except KeyboardInterrupt: sys.exit(0)
