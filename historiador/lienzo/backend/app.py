"""
Lienzo vivo del modulo de caudal MCC-09 - backend (FastAPI).  v1.0

- Sirve el knowledge graph (lectura y edicion con respaldo automatico).
- Estado y diagnostico en vivo o en cualquier momento pasado (maquina del tiempo), leyendo TimescaleDB con el
  rol de solo lectura mcp_lector.
- Reenvia por WebSocket lo que publica el UNS (MQTT) para los valores en vivo.
- Agente: Claude (Anthropic) o Gemini/otra API compatible con OpenAI + cliente MCP (stdio) del mismo
  servidor_mcp.py que usa Claude Desktop. Se elige con LLM_PROVEEDOR en el .env.
Ninguna ruta escribe en el PLC ni en la base de datos.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import psycopg
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

DB_DSN = os.getenv("DB_DSN", "postgresql://mcp_lector:lector_cambiar@localhost:5432/uns")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE = os.getenv("UNS_BASE", "uss/campus/lab-automatizacion/sl01la07/caudal-mcc09")
MCP_DIR = Path(os.getenv("MCP_DIR", Path(__file__).resolve().parents[2] / "mcp_servidor"))
GRAFO = MCP_DIR / "conocimiento" / "grafo_mcc09.json"
PROVEEDOR = os.getenv("LLM_PROVEEDOR", "anthropic").strip().lower()   # anthropic | gemini | openai (compatible)
PROVEEDORES = {
    "anthropic": {"clave": "ANTHROPIC_API_KEY", "modelo": os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), "url": None,
                  "nombre": "Anthropic"},
    "gemini": {"clave": "GEMINI_API_KEY", "modelo": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
               "url": "https://generativelanguage.googleapis.com/v1beta/openai/", "nombre": "Google Gemini"},
    "openai": {"clave": "LLM_API_KEY", "modelo": os.getenv("LLM_MODELO", ""), "url": os.getenv("LLM_BASE_URL"),
               "nombre": "API compatible con OpenAI"},
}
CFG = PROVEEDORES.get(PROVEEDOR, PROVEEDORES["anthropic"])
MODELO = CFG["modelo"]
STATIC = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[1] / "frontend" / "dist"))
TZ_LIMA = timezone(timedelta(hours=-5))
SLUG = re.compile(r"^[a-z0-9_]{1,40}$")
TIPOS = {"equipo", "sensor", "actuador", "control", "mando", "proteccion", "proceso"}

os.environ.setdefault("MCP_DSN", DB_DSN)
sys.path.insert(0, str(MCP_DIR))
import servidor_mcp as srv  # noqa: E402  (mismas reglas de diagnostico que el agente)


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime | None) -> str | None:
    return t.astimezone(TZ_LIMA).isoformat(timespec="seconds") if t else None


def parse_t(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"fecha no valida: {s}")
    return t if t.tzinfo else t.replace(tzinfo=TZ_LIMA)


def consulta(sql: str, params: dict | tuple = ()) -> list[dict]:
    with psycopg.connect(DB_DSN, row_factory=dict_row, connect_timeout=5,
                         options="-c default_transaction_read_only=on -c statement_timeout=8000") as con:
        with con.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


# ----------------------------------------------------------------------------- MQTT -> WebSocket
class Vivo:
    """Un cliente MQTT compartido; reparte cada mensaje a los WebSocket conectados."""

    def __init__(self):
        self.clientes: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.conectado = False
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"lienzo-{os.getpid()}")
        self.c.on_connect = self._on_connect
        self.c.on_disconnect = lambda *a: setattr(self, "conectado", False)
        self.c.on_message = self._on_message

    def iniciar(self, loop):
        self.loop = loop
        self.c.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.c.loop_start()

    def _on_connect(self, c, _u, _f, rc, _p=None):
        self.conectado = True
        c.subscribe(f"{BASE}/funcional/#", qos=0)

    def _on_message(self, _c, _u, msg):
        topic = msg.topic[len(BASE) + len("/funcional/"):]
        texto = msg.payload.decode("utf-8", "replace")
        try:
            d = json.loads(texto)
        except json.JSONDecodeError:
            d = None
        if isinstance(d, dict) and "value" in d:
            ev = {"tipo": "valor", "variable": topic, "valor": d["value"], "unidad": d.get("unit"),
                  "t": d.get("timestamp")}
        else:
            ev = {"tipo": "evento", "variable": topic, "texto": texto, "t": iso(ahora())}
        if self.loop:
            for q in list(self.clientes):
                self.loop.call_soon_threadsafe(q.put_nowait, ev)


vivo = Vivo()


@asynccontextmanager
async def lifespan(_app):
    vivo.iniciar(asyncio.get_running_loop())
    yield
    vivo.c.loop_stop()


app = FastAPI(title="Lienzo MCC-09", lifespan=lifespan)


# ----------------------------------------------------------------------------- API
@app.get("/api/salud")
def salud():
    try:
        consulta("SELECT 1")
        db = True
    except Exception:  # noqa: BLE001
        db = False
    return {"db": db, "mqtt": vivo.conectado, "agente": bool(os.getenv(CFG["clave"])), "modelo": MODELO,
            "proveedor": CFG["nombre"],
            "solo_lectura": True}


@app.get("/api/grafo")
def leer_grafo():
    return json.loads(GRAFO.read_text(encoding="utf-8"))


@app.put("/api/grafo")
async def guardar_grafo(req: Request):
    g = await req.json()
    nodos, rel = g.get("nodos"), g.get("relaciones")
    if not isinstance(nodos, dict) or not isinstance(rel, list) or not nodos:
        raise HTTPException(400, "Se esperan 'nodos' (objeto) y 'relaciones' (lista)")
    for k, n in nodos.items():
        if not SLUG.match(k):
            raise HTTPException(400, f"Id de nodo no valido: '{k}' (minusculas, digitos y _)")
        if n.get("tipo") not in TIPOS:
            raise HTTPException(400, f"Tipo no valido en '{k}': {n.get('tipo')}")
        if not str(n.get("nombre", "")).strip():
            raise HTTPException(400, f"El nodo '{k}' necesita nombre")
        if not isinstance(n.get("variables", []), list):
            raise HTTPException(400, f"'variables' de '{k}' debe ser una lista")
    vistos = set()
    for r in rel:
        if r.get("de") not in nodos or r.get("a") not in nodos:
            raise HTTPException(400, f"Relacion con nodo inexistente: {r}")
        if not SLUG.match(str(r.get("rel", ""))):
            raise HTTPException(400, f"Tipo de relacion no valido: {r.get('rel')}")
        clave = (r["de"], r["rel"], r["a"])
        if clave in vistos:
            raise HTTPException(400, f"Relacion repetida: {clave}")
        vistos.add(clave)
    actual = json.loads(GRAFO.read_text(encoding="utf-8"))
    respaldos = GRAFO.parent / "respaldos"
    respaldos.mkdir(exist_ok=True)
    marca = datetime.now(TZ_LIMA).strftime("%Y%m%d_%H%M%S")
    shutil.copy2(GRAFO, respaldos / f"grafo_mcc09_{marca}.json")
    nuevo = {**actual, "nodos": nodos, "relaciones": rel, "layout": g.get("layout", actual.get("layout", {})),
             "editado": iso(ahora())}
    tmp = GRAFO.with_suffix(".tmp")
    tmp.write_text(json.dumps(nuevo, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(GRAFO)
    return {"ok": True, "respaldo": f"respaldos/grafo_mcc09_{marca}.json", "nodos": len(nodos), "relaciones": len(rel)}


@app.get("/api/variables")
def variables():
    return srv.listar_variables()


@app.get("/api/rango")
def rango():
    f = consulta("SELECT min(time) AS desde, max(time) AS hasta FROM mediciones WHERE fuente = 'uns'")[0]
    return {"desde": iso(f["desde"]), "hasta": iso(f["hasta"])}


@app.get("/api/estado")
def estado(momento: str | None = None):
    t = parse_t(momento) or ahora()
    filas = consulta(
        """SELECT DISTINCT ON (variable) variable, valor, unidad, time FROM mediciones
           WHERE fuente = 'uns' AND time <= %(t)s AND time > %(t)s - interval '2 hours'
           ORDER BY variable, time DESC""", {"t": t})
    valores = {f["variable"]: {"valor": f["valor"], "unidad": f["unidad"], "t": iso(f["time"]),
                               "edad_s": round((t - f["time"]).total_seconds(), 1)} for f in filas}
    enlace = srv._estado_enlace() if momento is None else None
    return {"momento": iso(t), "en_vivo": momento is None, "valores": valores, "enlace": enlace}


@app.get("/api/diagnostico")
def diagnostico(momento: str | None = None):
    try:
        return srv.diagnosticar_lazo(momento)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@app.get("/api/historial")
def historial(variables: str, minutos: float = 30, inicio: str | None = None, fin: str | None = None,
              puntos: int = 300):
    vs = [v for v in variables.split(",") if v][:12]
    t1 = parse_t(fin) or ahora()
    t0 = parse_t(inicio) or (t1 - timedelta(minutes=minutos))
    paso = max(1, int((t1 - t0).total_seconds() / max(20, min(puntos, 1500))))
    filas = consulta(
        """SELECT variable, date_bin(make_interval(secs => %(p)s), time, %(t0)s) AS t, avg(valor) AS v
           FROM mediciones WHERE fuente = 'uns' AND variable = ANY(%(vs)s) AND time >= %(t0)s AND time < %(t1)s
           GROUP BY 1, 2 ORDER BY 1, 2""", {"p": paso, "t0": t0, "t1": t1, "vs": vs})
    series: dict[str, list] = {v: [] for v in vs}
    for f in filas:
        series[f["variable"]].append([iso(f["t"]), round(f["v"], 3)])
    return {"inicio": iso(t0), "fin": iso(t1), "paso_s": paso, "series": series}


@app.get("/api/eventos")
def eventos(inicio: str | None = None, fin: str | None = None, horas: float = 4):
    """Cambios de estado (bomba, modo) para marcar la linea de tiempo."""
    t1 = parse_t(fin) or ahora()
    t0 = parse_t(inicio) or (t1 - timedelta(hours=horas))
    filas = consulta(
        """SELECT variable, time, valor FROM (
             SELECT variable, time, valor, lag(valor) OVER (PARTITION BY variable ORDER BY time) AS prev
             FROM mediciones WHERE fuente = 'uns' AND time BETWEEN %(t0)s AND %(t1)s
               AND variable IN ('estado/sistema_funcionando', 'estado/selector_remoto', 'estado/nivel_bajo')) x
           WHERE prev IS DISTINCT FROM valor AND prev IS NOT NULL ORDER BY time""", {"t0": t0, "t1": t1})
    return [{"variable": f["variable"], "t": iso(f["time"]), "valor": f["valor"]} for f in filas]


@app.websocket("/ws/vivo")
async def ws_vivo(ws: WebSocket):
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    vivo.clientes.add(q)
    try:
        await ws.send_json({"tipo": "snapshot", **await asyncio.to_thread(estado)})
        while True:
            ev = await q.get()
            await ws.send_json(ev)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        vivo.clientes.discard(q)


# ----------------------------------------------------------------------------- agente (Claude + MCP)
SISTEMA_EXTRA = """Respondes dentro del lienzo visual del modulo de caudal MCC-09. Escribe en espanol, breve y
concreto: primero la conclusion con su numero y unidad, luego la evidencia. Usa siempre las herramientas antes de
afirmar algo del proceso. El sistema es de solo lectura: no puedes cambiar setpoints ni arrancar o parar equipos."""


def _bloque(b) -> dict:
    """Solo los campos que la API acepta de vuelta en el historial."""
    if b.type == "text":
        return {"type": "text", "text": b.text}
    return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}


def _causa(e: BaseException) -> BaseException:
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


def _mensaje_error(e: BaseException) -> str:
    nombre = type(e).__name__
    texto = str(e)
    bajo = texto.lower()
    clave = CFG["clave"]
    if nombre == "AuthenticationError" or "api key not valid" in bajo or "api_key_invalid" in bajo:
        return f"La clave de {CFG['nombre']} no es valida (revisa {clave} en el .env, sin comillas ni espacios)."
    if nombre == "PermissionDeniedError":
        return f"La clave de {CFG['nombre']} no tiene permiso para el modelo '{MODELO}'."
    if nombre == "NotFoundError" or "is not found" in bajo:
        return f"El modelo '{MODELO}' no existe en {CFG['nombre']} (revisa el modelo en el .env)."
    if nombre == "RateLimitError" or "resource_exhausted" in bajo or "quota" in bajo:
        return f"Se alcanzo el limite gratuito de {CFG['nombre']} (por minuto o por dia); espera un momento."
    if nombre in ("APIConnectionError", "APITimeoutError"):
        return f"No se pudo conectar con {CFG['nombre']} (revisa la conexion a internet de la laptop)."
    if "credit balance" in bajo:
        return "La cuenta de Anthropic no tiene saldo de API (Plans & Billing en console.anthropic.com)."
    return f"{nombre}: {texto}"[:500]


_CLAVES_ESQUEMA = {"type", "description", "properties", "items", "enum", "required", "format"}


def _esquema_compatible(x: Any) -> Any:
    """Gemini acepta un subconjunto de JSON Schema: quita title/default/additionalProperties y convierte
    anyOf [X, null] en X (marcado nullable)."""
    if isinstance(x, list):
        return [_esquema_compatible(v) for v in x]
    if not isinstance(x, dict):
        return x
    if "anyOf" in x:
        opciones = [o for o in x["anyOf"] if o.get("type") != "null"]
        base = dict(opciones[0]) if opciones else {"type": "string"}
        if "description" in x:
            base.setdefault("description", x["description"])
        out = _esquema_compatible(base)
        if len(opciones) < len(x["anyOf"]):
            out["nullable"] = True
        return out
    out = {}
    for k, v in x.items():
        if k == "properties":
            out[k] = {pk: _esquema_compatible(pv) for pk, pv in v.items()}
        elif k in _CLAVES_ESQUEMA:
            out[k] = _esquema_compatible(v)
    if out.get("type") == "object" and "properties" not in out:
        out["properties"] = {}
    return out


def _sse(d: dict) -> str:
    return f"data: {json.dumps(d, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/agente")
async def agente(req: Request):
    cuerpo = await req.json()
    historial_chat = [m for m in cuerpo.get("mensajes", []) if m.get("role") in ("user", "assistant")
                      and isinstance(m.get("content"), str) and m["content"].strip()][-12:]
    if not historial_chat or historial_chat[-1]["role"] != "user":
        raise HTTPException(400, "El ultimo mensaje debe ser del usuario")
    if not os.getenv(CFG["clave"]):
        raise HTTPException(503, f"Falta {CFG['clave']} en el archivo .env del historiador")

    async def flujo():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=sys.executable, args=[str(MCP_DIR / "servidor_mcp.py")],
                                       env={**os.environ, "MCP_DSN": DB_DSN})
        try:
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as sesion:
                    init = await sesion.initialize()
                    tools = (await sesion.list_tools()).tools
                    yield _sse({"tipo": "inicio", "modelo": MODELO, "proveedor": CFG["nombre"], "herramientas": len(tools)})
                    sistema = (init.instructions or "") + "\n\n" + SISTEMA_EXTRA

                    async def ejecutar(uid: str, nombre: str, entrada: dict):
                        """Llama la herramienta MCP; devuelve (eventos SSE, texto para el modelo, es_error)."""
                        t0 = asyncio.get_running_loop().time()
                        res = await sesion.call_tool(nombre, entrada)
                        texto = "".join(getattr(c, "text", "") for c in res.content)
                        ms = round((asyncio.get_running_loop().time() - t0) * 1000)
                        try:
                            datos = json.loads(texto)
                        except json.JSONDecodeError:
                            datos = None
                        return (_sse({"tipo": "resultado", "id": uid, "nombre": nombre, "ms": ms,
                                      "error": bool(res.is_error), "datos": datos}), texto, bool(res.is_error))

                    if PROVEEDOR == "anthropic":
                        import anthropic
                        cliente = anthropic.AsyncAnthropic()
                        herramientas = [{"name": t.name, "description": t.description or "",
                                         "input_schema": t.input_schema} for t in tools]
                        msgs: list[dict[str, Any]] = [dict(m) for m in historial_chat]
                        for _ in range(8):
                            async with cliente.messages.stream(model=MODELO, max_tokens=1500, system=sistema,
                                                               tools=herramientas, messages=msgs) as st:
                                async for ev in st:
                                    if ev.type == "text":
                                        yield _sse({"tipo": "texto", "delta": ev.text})
                                final = await st.get_final_message()
                            msgs.append({"role": "assistant",
                                         "content": [_bloque(b) for b in final.content if b.type in ("text", "tool_use")]})
                            usos = [b for b in final.content if b.type == "tool_use"]
                            if not usos:
                                break
                            resultados = []
                            for u in usos:
                                yield _sse({"tipo": "herramienta", "id": u.id, "nombre": u.name, "entrada": u.input})
                                ev_res, texto, err = await ejecutar(u.id, u.name, u.input)
                                yield ev_res
                                resultados.append({"type": "tool_result", "tool_use_id": u.id,
                                                   "content": texto[:60000], "is_error": err})
                            msgs.append({"role": "user", "content": resultados})
                    else:
                        # Gemini u otra API compatible con OpenAI (chat.completions + tools)
                        from openai import AsyncOpenAI
                        cliente = AsyncOpenAI(api_key=os.getenv(CFG["clave"]), base_url=CFG["url"])
                        herramientas = [{"type": "function", "function": {
                            "name": t.name, "description": (t.description or "")[:1000],
                            "parameters": _esquema_compatible(t.input_schema)}} for t in tools]
                        msgs = [{"role": "system", "content": sistema}] + [dict(m) for m in historial_chat]
                        for _ in range(8):
                            resp = await cliente.chat.completions.create(model=MODELO, messages=msgs, tools=herramientas,
                                                                         tool_choice="auto")
                            m = resp.choices[0].message
                            llamadas = m.tool_calls or []
                            if m.content and not llamadas:
                                yield _sse({"tipo": "texto", "delta": m.content})
                            msgs.append({"role": "assistant", "content": m.content or "", **({"tool_calls": [
                                {"id": c.id, "type": "function",
                                 "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                                for c in llamadas]} if llamadas else {})})
                            if not llamadas:
                                break
                            for c in llamadas:
                                try:
                                    entrada = json.loads(c.function.arguments or "{}") or {}
                                except json.JSONDecodeError:
                                    entrada = {}
                                entrada = {k: v for k, v in entrada.items() if v is not None}
                                yield _sse({"tipo": "herramienta", "id": c.id, "nombre": c.function.name, "entrada": entrada})
                                ev_res, texto, err = await ejecutar(c.id, c.function.name, entrada)
                                yield ev_res
                                msgs.append({"role": "tool", "tool_call_id": c.id, "content": texto[:60000]})
            yield _sse({"tipo": "fin"})
        except BaseException as e:  # noqa: BLE001  (los grupos de excepciones de anyio esconden la causa real)
            causa = _causa(e)
            print(f"[agente] error: {causa!r}", flush=True)
            yield _sse({"tipo": "error", "detalle": _mensaje_error(causa)})

    return StreamingResponse(flujo(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ----------------------------------------------------------------------------- frontend
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{ruta:path}")
    def spa(ruta: str):
        f = STATIC / ruta
        if ruta and f.is_file() and STATIC in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
else:
    @app.get("/")
    def sin_frontend():
        return JSONResponse({"aviso": "frontend no compilado", "static": str(STATIC)})
