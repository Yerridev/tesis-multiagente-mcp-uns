"""
Ingestor UNS -> TimescaleDB.
Se suscribe a <BASE>/funcional/# y <BASE>/descriptivo/variables y guarda:
  - mediciones numericas/booleanas -> tabla mediciones (fuente='uns')
  - mensajes de texto (ONLINE, CONECTADO, heartbeat) -> tabla eventos
  - catalogo de variables -> tabla variables
Inserta por lotes (cada segundo o cada 200 mensajes) para no saturar la base.
"""
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psycopg

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE = os.getenv("UNS_BASE", "uss/campus/lab-automatizacion/sl01la07/caudal-mcc09")
DB_DSN = os.getenv("DB_DSN", "postgresql://uns_admin:cambiar_esto@localhost:5432/uns")
# Prefijo opcional para el nombre de variable (p. ej. "nivel-mcn09/") cuando varios equipos comparten la base.
# Vacio = comportamiento original (caudal).
VAR_PREFIX = os.getenv("VAR_PREFIX", "")
CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "uns-ingestor-timescale")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingestor")
cola: "queue.Queue[tuple]" = queue.Queue(maxsize=50_000)


def interpretar(topic: str, payload: bytes):
    """Convierte un mensaje MQTT en ('medicion', fila) | ('evento', fila) | ('catalogo', lista) | None."""
    texto = payload.decode("utf-8", errors="replace").strip()
    if topic == f"{BASE}/descriptivo/variables":
        try:
            return ("catalogo", json.loads(texto))
        except json.JSONDecodeError:
            return None
    prefijo = f"{BASE}/funcional/"
    if not topic.startswith(prefijo):
        return None
    variable = VAR_PREFIX + topic[len(prefijo):]
    try:
        dato = json.loads(texto)
    except json.JSONDecodeError:
        dato = None
    if isinstance(dato, dict) and "value" in dato:
        v = dato["value"]
        if isinstance(v, bool):
            v = 1.0 if v else 0.0
        elif not isinstance(v, (int, float)):
            return ("evento", (datetime.now(timezone.utc), topic, texto))
        ts = dato.get("timestamp")
        t = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
        direccion = (dato.get("source") or "").split("/")[-1] or None
        return ("medicion", (t, variable, float(v), dato.get("unit"), "uns", direccion))
    return ("evento", (datetime.now(timezone.utc), topic, texto))


def al_conectar(cliente, _u, _f, rc, _p=None):
    log.info("MQTT conectado a %s:%s (rc=%s)", MQTT_HOST, MQTT_PORT, rc)
    cliente.subscribe(f"{BASE}/funcional/#", qos=1)
    cliente.subscribe(f"{BASE}/descriptivo/variables", qos=1)


def al_recibir(_c, _u, msg):
    r = interpretar(msg.topic, msg.payload)
    if r:
        try:
            cola.put_nowait(r)
        except queue.Full:
            log.warning("Cola llena; se descarta un mensaje")


def guardar_catalogo(con, lista):
    with con.cursor() as cur:
        for t in lista:
            cur.execute(
                """INSERT INTO variables (variable, tag_plc, direccion, unidad, descripcion, actualizado)
                   VALUES (%s, %s, %s, %s, %s, now())
                   ON CONFLICT (variable) DO UPDATE SET tag_plc = EXCLUDED.tag_plc,
                     direccion = EXCLUDED.direccion, unidad = EXCLUDED.unidad,
                     descripcion = EXCLUDED.descripcion, actualizado = now()""",
                (VAR_PREFIX + (t.get("topic") or ""), t.get("n"), t.get("dir"), t.get("unidad"), t.get("desc")))
    con.commit()


def escritor():
    while True:
        try:
            with psycopg.connect(DB_DSN) as con:
                log.info("Conectado a la base de datos")
                while True:
                    mediciones, eventos = [], []
                    limite = time.time() + 1.0
                    while time.time() < limite and len(mediciones) + len(eventos) < 200:
                        try:
                            tipo, fila = cola.get(timeout=0.2)
                        except queue.Empty:
                            continue
                        if tipo == "medicion":
                            mediciones.append(fila)
                        elif tipo == "evento":
                            eventos.append(fila)
                        elif tipo == "catalogo":
                            guardar_catalogo(con, fila)
                    if mediciones or eventos:
                        with con.cursor() as cur:
                            if mediciones:
                                cur.executemany(
                                    """INSERT INTO mediciones (time, variable, valor, unidad, fuente, direccion)
                                       VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""", mediciones)
                            if eventos:
                                cur.executemany("INSERT INTO eventos (time, topic, texto) VALUES (%s, %s, %s)", eventos)
                        con.commit()
                        log.info("Guardadas %d mediciones, %d eventos", len(mediciones), len(eventos))
        except psycopg.OperationalError as e:
            log.error("Base de datos no disponible: %s. Reintento en 5 s", e)
            time.sleep(5)


def main():
    threading.Thread(target=escritor, daemon=True).start()
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    c.on_connect = al_conectar
    c.on_message = al_recibir
    while True:
        try:
            c.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except OSError as e:
            log.error("Broker MQTT no disponible (%s). Reintento en 5 s", e)
            time.sleep(5)
    c.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
