"""Piezas compartidas por los agentes: configuración, LLM (OpenRouter), MQTT y trazas."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "mcp"))
from modulos import MODULOS, UNS  # noqa: E402,F401

LIMA = timezone(timedelta(hours=-5))
TOPICO = f"{UNS}/agentes"


def _env_archivo() -> dict:
    """Lee el .env del proyecto (sin pisar variables ya definidas)."""
    d = {}
    try:
        for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                d[k.strip()] = v.strip()
    except OSError:
        pass
    return d


_ENV = _env_archivo()


def cfg(clave: str, defecto: str = "") -> str:
    return os.environ.get(clave) or _ENV.get(clave) or defecto


MQTT_HOST = cfg("AGENTES_MQTT_HOST", "127.0.0.1")
MQTT_PUERTO = int(cfg("AGENTES_MQTT_PUERTO", "1883"))
MCP_HOST = cfg("AGENTES_MCP_HOST", "127.0.0.1")


def url_mcp(modulo: str) -> str:
    return f"http://{MCP_HOST}:{MODULOS[modulo]['puerto']}/sse"


def ahora() -> str:
    return datetime.now(LIMA).isoformat(timespec="milliseconds")


def nuevo_id() -> str:
    return datetime.now(LIMA).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


# ------------------------------------------------------------------ trazas (trazabilidad)
_TRAZA_DIR = Path(cfg("AGENTES_TRAZAS", str(RAIZ / "registros" / "agentes")))
_traza_lock = threading.Lock()


def traza(evento: str, **datos) -> None:
    """Una línea JSON por evento: quién, qué, cuándo, cuánto tardó. Base del índice de trazabilidad."""
    fila = {"ts": ahora(), "evento": evento, **datos}
    try:
        _TRAZA_DIR.mkdir(parents=True, exist_ok=True)
        with _traza_lock, open(_TRAZA_DIR / f"{datetime.now(LIMA):%Y%m%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ LLM
class LLM:
    """Cliente OpenAI-compatible de OpenRouter. Sin clave → None (los agentes usan reglas)."""

    def __init__(self, modelo: str | None = None):
        self.clave = cfg("OPENROUTER_API_KEY")
        self.modelo = modelo or cfg("AGENTES_MODELO") or cfg("OPENROUTER_MODEL", "openrouter/free")
        self.url = cfg("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")

    @property
    def disponible(self) -> bool:
        return bool(self.clave)

    def chat(self, mensajes: list[dict], herramientas: list[dict] | None = None, timeout: float = 90) -> dict:
        cuerpo = {"model": self.modelo, "messages": mensajes, "temperature": 0.2}
        if herramientas:
            cuerpo["tools"] = herramientas
        r = httpx.post(self.url, json=cuerpo, timeout=timeout,
                       headers={"Authorization": f"Bearer {self.clave}", "X-Title": "MCP-INDUSTRIAL agentes"})
        r.raise_for_status()
        d = r.json()
        if "choices" not in d:
            raise RuntimeError(str(d.get("error") or d)[:300])
        msg = d["choices"][0]["message"]
        msg["_modelo"] = d.get("model", self.modelo)
        return msg


def extraer_json(texto: str) -> dict | None:
    """Toma el primer objeto JSON de un texto del LLM (puede venir en ```json)."""
    if not texto:
        return None
    i, j = texto.find("{"), texto.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(texto[i:j + 1])
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------ MQTT
def cliente_mqtt(nombre: str) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{nombre}-{uuid.uuid4().hex[:6]}")
    c.reconnect_delay_set(1, 10)
    return c


def conectar(c: mqtt.Client, al_conectar=None) -> None:
    """Conecta y re-suscribe en cada reconexión (lección del conector de caudal)."""
    def on_connect(cli, _u, _f, rc, _p=None):
        if not rc.is_failure and al_conectar:
            al_conectar(cli)
    c.on_connect = on_connect
    while True:
        try:
            c.connect(MQTT_HOST, MQTT_PUERTO, keepalive=30)
            break
        except OSError as ex:
            print(f"[mqtt] {MQTT_HOST}:{MQTT_PUERTO} no responde ({ex}); reintento en 3 s", flush=True)
            time.sleep(3)
    c.loop_start()
