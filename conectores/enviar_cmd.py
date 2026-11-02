#!/usr/bin/env python3
"""
Herramienta de laboratorio: publica una orden en {base}/control/cmd y espera el ack.

Ejemplos:
  python enviar_cmd.py --tipo Iniciar
  python enviar_cmd.py --tipo Setpoint --valor 20
  python enviar_cmd.py --tipo ParametroPid --parametro kp --valor 2.5
"""

from __future__ import annotations

import argparse
import json
import socket
import time
import uuid

import paho.mqtt.client as mqtt

BASE = "uss/campus/lab-automatizacion/sl01la07/nivel-mcn09/control"


def main() -> int:
    ap = argparse.ArgumentParser(description="Envía una orden de control de nivel y espera el ack")
    ap.add_argument("--broker", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=1883)
    ap.add_argument("--tipo", required=True)
    ap.add_argument("--valor", type=float, default=None)
    ap.add_argument("--parametro", default=None)
    ap.add_argument("--espera", type=float, default=8.0)
    a = ap.parse_args()

    oid = uuid.uuid4().hex[:16]
    ahora = time.time()
    orden = {
        "id": oid,
        "equipo": "nivel-mcn09",
        "tipo": a.tipo,
        "parametro": a.parametro,
        "valor": a.valor,
        "expedida": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "expira": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ahora + 15)),
        "modo": "LAB",
        "origen": {"usuario": "laboratorio", "rol": "supervisor"},
    }

    recibido = {"ok": False}

    try:
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"enviar-cmd-{socket.gethostname()}")
    except AttributeError:
        cli = mqtt.Client(client_id=f"enviar-cmd-{socket.gethostname()}")

    def on_connect(client, userdata, flags, reason_code, properties=None):
        client.subscribe(f"{BASE}/ack", qos=1)
        client.publish(f"{BASE}/cmd", json.dumps(orden), qos=1)
        print(f"[CMD] publicada id={oid} tipo={a.tipo} valor={a.valor}", flush=True)

    def on_message(client, userdata, msg):
        try:
            ack = json.loads(msg.payload.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return
        if ack.get("id") != oid:
            return
        print("[ACK] " + json.dumps(ack, ensure_ascii=False), flush=True)
        recibido["ok"] = True
        client.disconnect()

    cli.on_connect = on_connect
    cli.on_message = on_message
    cli.connect(a.broker, a.puerto, keepalive=30)
    cli.loop_start()
    limite = time.time() + a.espera
    try:
        while not recibido["ok"] and time.time() < limite:
            time.sleep(0.2)
    finally:
        cli.loop_stop()
        try:
            cli.disconnect()
        except Exception:
            pass
    if not recibido["ok"]:
        print("[TIMEOUT] sin ack (¿conector de control corriendo?)", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
