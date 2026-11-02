#!/usr/bin/env python3
"""
Ingestor de telemetría del módulo de NIVEL (MCN-09) → TimescaleDB.

- Se suscribe al UNS del nivel (funcional/# y descriptivo/#) por MQTT.
- Valida topic, equipo, timestamp, calidad y unidad antes de persistir.
- Idempotente: PRIMARY KEY (senal_id, ts) + ON CONFLICT DO UPDATE.
- Reconexión con backoff (paho reconnect_delay_set).
- Health HTTP en /healthz (para el healthcheck de Docker).
- Logs estructurados (JSON por línea) en stdout.
- NUNCA publica comandos: solo suscripción (modo lectura).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt
import psycopg

EQUIPO = os.environ.get("INGESTOR_EQUIPO", "nivel-mcn09")
BASE = f"uss/campus/lab-automatizacion/sl01la07/{EQUIPO}"
DB_DSN = os.environ.get(
    "DB_DSN",
    "postgresql://ingestor@timescaledb:5432/mcpindustrial",
)
SALUD_PUERTO = int(os.environ.get("INGESTOR_SALUD_PUERTO", "8099"))
TZ_OFFSET = -5  # America/Lima


def log(nivel: str, **campos) -> None:
    registro = {"ts": datetime.now(timezone.utc).isoformat(), "nivel": nivel, **campos}
    print(json.dumps(registro, ensure_ascii=False), flush=True)


class Estado:
    def __init__(self) -> None:
        self.mqtt = False
        self.db = False
        self.mensajes = 0
        self.escrituras = 0
        self.descartados = 0
        self.ultimo_mensaje = None
        self.ultimo_error = None


ESTADO = Estado()


class SaludHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        listo = ESTADO.mqtt and ESTADO.db
        cuerpo = json.dumps(
            {
                "status": "ok" if listo else "degraded",
                "mqtt": ESTADO.mqtt,
                "db": ESTADO.db,
                "mensajes": ESTADO.mensajes,
                "escrituras": ESTADO.escrituras,
                "descartados": ESTADO.descartados,
                "ultimo_mensaje": ESTADO.ultimo_mensaje,
                "ultimo_error": ESTADO.ultimo_error,
                "equipo": EQUIPO,
            }
        ).encode()
        self.send_response(200 if listo else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args):  # silencio
        pass


def conectar_db():
    """Reintenta la conexión con backoff creciente (1..30 s)."""
    espera = 1.0
    while True:
        try:
            conn = psycopg.connect(DB_DSN, autocommit=False)
            log("info", evento="db_conectado", dsn=DB_DSN.split("@")[-1])
            ESTADO.db = True
            return conn
        except Exception as ex:  # noqa: BLE001
            ESTADO.db = False
            ESTADO.ultimo_error = f"db:{ex}"
            log("warn", evento="db_reintento", error=str(ex), espera_s=espera)
            time.sleep(espera)
            espera = min(espera * 2, 30.0)


def preparar(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO equipos (equipo, nombre) VALUES (%s, %s)
            ON CONFLICT (equipo) DO UPDATE SET nombre = EXCLUDED.nombre
            RETURNING id
            """,
            (EQUIPO, f"Control de nivel {EQUIPO}"),
        )
        equipo_id = cur.fetchone()[0]
    conn.commit()
    return equipo_id


def upsert_senal(conn, equipo_id: int, nombre: str, unidad: str | None, source: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO senales (equipo_id, nombre, unidad, source)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (equipo_id, nombre)
            DO UPDATE SET unidad = COALESCE(EXCLUDED.unidad, senales.unidad),
                          source  = COALESCE(EXCLUDED.source, senales.source)
            RETURNING id
            """,
            (equipo_id, nombre, unidad, source),
        )
        senal_id = cur.fetchone()[0]
    conn.commit()
    return senal_id


def guardar(conn, senal_id: int, ts: datetime, valor: float, calidad: str, source: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mediciones (senal_id, ts, valor, calidad, source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (senal_id, ts)
            DO UPDATE SET valor = EXCLUDED.valor, calidad = EXCLUDED.calidad, source = EXCLUDED.source
            """,
            (senal_id, ts, valor, calidad, source),
        )
    conn.commit()
    ESTADO.escrituras += 1


def parsear_ts(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(TZ_OFFSET))
        return dt
    except ValueError:
        return None


def main() -> int:
    conn = conectar_db()
    equipo_id = preparar(conn)
    senales: dict[str, int] = {}

    servidor_salud = ThreadingHTTPServer(("0.0.0.0", SALUD_PUERTO), SaludHandler)
    threading.Thread(target=servidor_salud.serve_forever, daemon=True).start()
    log("info", evento="salud_inicio", puerto=SALUD_PUERTO)

    def on_connect(client, userdata, flags, reason_code, properties=None):
        ESTADO.mqtt = True
        client.subscribe(f"{BASE}/#", qos=1)
        log("info", evento="mqtt_conectado", topico=f"{BASE}/#")

    def on_disconnect(client, userdata, *args):
        ESTADO.mqtt = False
        log("warn", evento="mqtt_desconectado")

    def on_message(client, userdata, msg):
        nonlocal conn
        ESTADO.mensajes += 1
        ESTADO.ultimo_mensaje = datetime.now(timezone.utc).isoformat()
        topico = msg.topic
        if not topico.startswith(BASE):
            ESTADO.descartados += 1
            return
        sufijo = topico[len(BASE):].strip("/")
        # solo funcional/* y descriptivo/*; control/* (acks/estado) y edge/* no son mediciones
        if sufijo.startswith("control/") or sufijo.startswith("edge/"):
            return  # tráfico de control/estado: no es telemetría, no cuenta como descarte
        if not (sufijo.startswith("funcional/") or sufijo.startswith("descriptivo/")):
            ESTADO.descartados += 1
            return
        if sufijo.startswith("descriptivo/"):
            return  # catálogo/metadatos: no es medición
        nombre = sufijo[len("funcional/"):] if sufijo.startswith("funcional/") else sufijo
        cuerpo = msg.payload.decode("utf-8", "replace").strip()

        valor = None
        unidad = None
        source = None
        tag = None
        ts = None
        calidad = "ok"
        if cuerpo.startswith("{"):
            try:
                data = json.loads(cuerpo)
                valor = data.get("value")
                unidad = data.get("unit")
                source = data.get("source")
                tag = data.get("tag")
                ts = parsear_ts(data.get("timestamp"))
            except json.JSONDecodeError:
                calidad = "json_invalido"
        else:
            try:
                valor = float(cuerpo)
            except ValueError:
                calidad = "no_numerico"

        if calidad != "ok" or not isinstance(valor, (int, float)):
            ESTADO.descartados += 1
            log("warn", evento="descartado", topico=topico, calidad=calidad)
            return

        # estados booleanos via MQTT llegan como true/false en JSON → ya cubiertos;
        # los plain "true"/"false" se convierten a 1/0
        if isinstance(valor, bool):
            valor = 1.0 if valor else 0.0

        ts = ts or datetime.now(timezone.utc)
        try:
            if nombre not in senales:
                senales[nombre] = upsert_senal(conn, equipo_id, nombre, unidad, source or tag)
            guardar(conn, senales[nombre], ts, float(valor), calidad, source or tag)
        except Exception as ex:  # noqa: BLE001
            ESTADO.ultimo_error = f"insert:{ex}"
            log("error", evento="insert_fallido", error=str(ex))
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            conn = conectar_db()
            senales.clear()

    try:
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ingestor-{EQUIPO}")
    except AttributeError:
        cli = mqtt.Client(client_id=f"ingestor-{EQUIPO}")
    cli.reconnect_delay_set(min_delay=1, max_delay=60)
    cli.on_connect = on_connect
    cli.on_disconnect = on_disconnect
    cli.on_message = on_message

    host = os.environ.get("MQTT_HOST", "mosquitto")
    puerto = int(os.environ.get("MQTT_PORT", "1883"))
    log("info", evento="inicio", equipo=EQUIPO, mqtt=f"{host}:{puerto}")

    def salir(*_args):
        log("info", evento="parada")
        try:
            cli.loop_stop()
            cli.disconnect()
        except Exception:  # noqa: BLE001
            pass
        servidor_salud.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, salir)
    signal.signal(signal.SIGINT, salir)

    while True:
        try:
            cli.connect(host, puerto, keepalive=30)
            cli.loop_start()
            while True:
                time.sleep(1)
        except Exception as ex:  # noqa: BLE001
            ESTADO.mqtt = False
            ESTADO.ultimo_error = f"mqtt:{ex}"
            log("warn", evento="mqtt_reintento", error=str(ex))
            time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
