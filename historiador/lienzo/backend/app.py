"""
Lienzo vivo multi-equipo del laboratorio USS - backend (FastAPI).  v2.0

- Lee el registro de equipos (mcp_servidor/conocimiento/equipos.json): cada equipo trae su base UNS, su prefijo en
  la base de datos, su servidor MCP, su diagnostico y su knowledge graph. Agregar un PLC = agregar una entrada.
- Vista de planta (/api/planta): resumen de todos los equipos para la pantalla de inicio.
- Rutas por equipo (/api/e/{id}/...): grafo (lectura/edicion con respaldo), estado y diagnostico en vivo o en un
  momento pasado, historial, eventos y WebSocket del UNS.
- Agente: un solo chat que abre como cliente MCP (stdio) los servidores de TODOS los equipos registrados; las
  herramientas llevan el prefijo del equipo (caudal__..., nivel__...) para que el modelo coordine entre ellos.
Ninguna ruta escribe en los PLC ni en la base de datos (rol mcp_lector, sesiones read-only).
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import shutil
import sys
from contextlib import AsyncExitStack, asynccontextmanager
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
MCP_DIR = Path(os.getenv("MCP_DIR", Path(__file__).resolve().parents[2] / "mcp_servidor"))
CONOCIMIENTO = MCP_DIR / "conocimiento"
REGISTRO = CONOCIMIENTO / "equipos.json"
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


# ----------------------------------------------------------------------------- registro de equipos
def _leer_registro() -> dict:
    reg = json.loads(REGISTRO.read_text(encoding="utf-8"))
    ids = [e["id"] for e in reg["equipos"]]
    if len(ids) != len(set(ids)):
        raise RuntimeError("equipos.json tiene ids repetidos")
    return reg


REG = _leer_registro()
EQUIPOS: dict[str, dict] = {e["id"]: e for e in REG["equipos"]}
MODULOS: dict[str, Any] = {}
for _e in REG["equipos"]:
    try:
        MODULOS[_e["id"]] = importlib.import_module(_e["mcp_modulo"])  # mismas reglas que usa el agente
    except Exception as _err:  # noqa: BLE001  (un equipo mal configurado no debe tumbar el lienzo)
        print(f"[lienzo] no se pudo cargar {_e['mcp_modulo']} ({_e['id']}): {_err!r}", flush=True)


def eq(equipo: str) -> dict:
    cfg = EQUIPOS.get(equipo)
    if not cfg:
        raise HTTPException(404, f"Equipo '{equipo}' no registrado. Opciones: {', '.join(EQUIPOS)}")
    return cfg


def modulo(cfg: dict):
    m = MODULOS.get(cfg["id"])
    if m is None:
        raise HTTPException(503, f"El servidor MCP de {cfg['id']} ({cfg['mcp_modulo']}) no se pudo cargar")
    return m


def largo(cfg: dict, v: str) -> str:
    return cfg["prefijo_db"] + v


def corto(cfg: dict, v: str) -> str:
    p = cfg["prefijo_db"]
    return v[len(p):] if p and v.startswith(p) else v


def filtro(cfg: dict) -> tuple[str, dict]:
    """Fragmento SQL que deja solo las variables de este equipo en la tabla mediciones."""
    if cfg["prefijo_db"]:
        return "variable LIKE %(pfx)s", {"pfx": cfg["prefijo_db"] + "%"}
    otros = [e["prefijo_db"] + "%" for e in EQUIPOS.values() if e["prefijo_db"]]
    return ("NOT (variable LIKE ANY(%(otros)s))", {"otros": otros}) if otros else ("TRUE", {})


def grafo_path(cfg: dict) -> Path:
    return CONOCIMIENTO / cfg["grafo"]


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
    """Un cliente MQTT compartido para todos los equipos; reparte cada mensaje a los WebSocket de ese equipo."""

    def __init__(self):
        self.clientes: dict[asyncio.Queue, str] = {}
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
        for e in EQUIPOS.values():
            c.subscribe(f"{e['uns_base']}/funcional/#", qos=0)

    def _on_message(self, _c, _u, msg):
        cfg = next((e for e in EQUIPOS.values() if msg.topic.startswith(e["uns_base"] + "/funcional/")), None)
        if not cfg:
            return
        topic = msg.topic[len(cfg["uns_base"]) + len("/funcional/"):]
        texto = msg.payload.decode("utf-8", "replace")
        try:
            d = json.loads(texto)
        except json.JSONDecodeError:
            d = None
        if isinstance(d, dict) and "value" in d:
            ev = {"tipo": "valor", "equipo": cfg["id"], "variable": topic, "valor": d["value"], "unidad": d.get("unit"),
                  "t": d.get("timestamp")}
        else:
            ev = {"tipo": "evento", "equipo": cfg["id"], "variable": topic, "texto": texto, "t": iso(ahora())}
        if self.loop:
            for q, quien in list(self.clientes.items()):
                if quien in ("*", cfg["id"]):
                    self.loop.call_soon_threadsafe(q.put_nowait, ev)


vivo = Vivo()


@asynccontextmanager
async def lifespan(_app):
    vivo.iniciar(asyncio.get_running_loop())
    yield
    vivo.c.loop_stop()


app = FastAPI(title="Lienzo del laboratorio USS", lifespan=lifespan)


# ----------------------------------------------------------------------------- API general
@app.get("/api/salud")
def salud():
    try:
        consulta("SELECT 1")
        db = True
    except Exception:  # noqa: BLE001
        db = False
    return {"db": db, "mqtt": vivo.conectado, "agente": bool(os.getenv(CFG["clave"])), "modelo": MODELO,
            "proveedor": CFG["nombre"], "solo_lectura": True,
            "equipos_cargados": [k for k in EQUIPOS if k in MODULOS]}


@app.get("/api/equipos")
def equipos():
    publicos = [{k: v for k, v in e.items() if k not in ("mcp_modulo",)} | {"disponible": e["id"] in MODULOS}
                for e in REG["equipos"]]
    return {"organizacion": REG.get("organizacion", {}), "equipos": publicos}


def _ultimos(cfg: dict, vs: list[str], t: datetime | None = None) -> dict[str, dict]:
    t = t or ahora()
    filas = consulta(
        """SELECT DISTINCT ON (variable) variable, valor, unidad, time FROM mediciones
           WHERE fuente = 'uns' AND variable = ANY(%(vs)s) AND time <= %(t)s AND time > %(t)s - interval '1 day'
           ORDER BY variable, time DESC""", {"vs": [largo(cfg, v) for v in vs], "t": t})
    return {corto(cfg, f["variable"]): f for f in filas}


def _diagnostico(cfg: dict, momento: str | None) -> dict:
    d = getattr(modulo(cfg), cfg["diagnostico"])(momento)
    d.setdefault("cadena_causal", [])
    d.setdefault("aristas_causales", [])
    d.setdefault("hallazgos_secundarios", [])
    d.setdefault("evidencia", {})
    return d


def _resumen(cfg: dict) -> dict:
    p = cfg["principal"]
    s = cfg.get("secundario")
    salida: dict[str, Any] = {"id": cfg["id"], "disponible": cfg["id"] in MODULOS}
    try:
        salida["enlace"] = modulo(cfg)._estado_enlace()
    except Exception as e:  # noqa: BLE001
        salida["enlace"] = None
        salida["error"] = str(e)[:200]
        return salida
    vs = [p["variable"], cfg["marcha"], "estado/selector_remoto", "estado/selector_local"] + ([s["variable"]] if s else [])
    u = _ultimos(cfg, vs)
    salida["valores"] = {k: {"valor": f["valor"], "unidad": f["unidad"], "t": iso(f["time"])} for k, f in u.items()}
    try:
        d = _diagnostico(cfg, None)
        salida["diagnostico"] = {k: d.get(k) for k in ("diagnostico", "explicacion", "recomendacion")}
    except Exception as e:  # noqa: BLE001
        salida["diagnostico"] = {"diagnostico": "ERROR", "explicacion": str(e)[:200], "recomendacion": ""}
    t1 = ahora()
    t0 = t1 - timedelta(minutes=30)
    spark = consulta(
        """SELECT date_bin('30 seconds', time, %(t0)s) AS t, avg(valor) AS v FROM mediciones
           WHERE fuente = 'uns' AND variable = %(v)s AND time >= %(t0)s AND time < %(t1)s GROUP BY 1 ORDER BY 1""",
        {"v": largo(cfg, p["variable"]), "t0": t0, "t1": t1})
    salida["spark"] = [[iso(f["t"]), round(f["v"], 3)] for f in spark]
    return salida


@app.get("/api/planta")
async def planta():
    """Resumen de todos los equipos (tarjetas de la vista general). Se calcula en paralelo."""
    res = await asyncio.gather(*(asyncio.to_thread(_resumen, e) for e in REG["equipos"]), return_exceptions=True)
    return {"consultado": iso(ahora()),
            "equipos": [r if isinstance(r, dict) else {"id": e["id"], "error": str(r)[:200]}
                        for e, r in zip(REG["equipos"], res)]}


# ----------------------------------------------------------------------------- API por equipo
@app.get("/api/e/{equipo}/grafo")
def leer_grafo(equipo: str):
    return json.loads(grafo_path(eq(equipo)).read_text(encoding="utf-8"))


@app.put("/api/e/{equipo}/grafo")
async def guardar_grafo(equipo: str, req: Request):
    cfg = eq(equipo)
    ruta = grafo_path(cfg)
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
    actual = json.loads(ruta.read_text(encoding="utf-8"))
    respaldos = ruta.parent / "respaldos"
    respaldos.mkdir(exist_ok=True)
    marca = datetime.now(TZ_LIMA).strftime("%Y%m%d_%H%M%S")
    nombre_resp = f"{ruta.stem}_{marca}.json"
    shutil.copy2(ruta, respaldos / nombre_resp)
    nuevo = {**actual, "nodos": nodos, "relaciones": rel, "layout": g.get("layout", actual.get("layout", {})),
             "editado": iso(ahora())}
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(nuevo, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)
    return {"ok": True, "respaldo": f"respaldos/{nombre_resp}", "nodos": len(nodos), "relaciones": len(rel)}


@app.get("/api/e/{equipo}/variables")
def variables(equipo: str):
    return modulo(eq(equipo)).listar_variables()


@app.get("/api/e/{equipo}/rango")
def rango(equipo: str):
    cfg = eq(equipo)
    w, p = filtro(cfg)
    f = consulta(f"SELECT min(time) AS desde, max(time) AS hasta FROM mediciones WHERE fuente = 'uns' AND {w}", p)[0]
    return {"desde": iso(f["desde"]), "hasta": iso(f["hasta"])}


@app.get("/api/e/{equipo}/estado")
def estado(equipo: str, momento: str | None = None):
    cfg = eq(equipo)
    t = parse_t(momento) or ahora()
    w, p = filtro(cfg)
    filas = consulta(
        f"""SELECT DISTINCT ON (variable) variable, valor, unidad, time FROM mediciones
            WHERE fuente = 'uns' AND {w} AND time <= %(t)s AND time > %(t)s - interval '2 hours'
            ORDER BY variable, time DESC""", {"t": t, **p})
    valores = {corto(cfg, f["variable"]): {"valor": f["valor"], "unidad": f["unidad"], "t": iso(f["time"]),
                                           "edad_s": round((t - f["time"]).total_seconds(), 1)} for f in filas}
    enlace = modulo(cfg)._estado_enlace() if momento is None else None
    return {"equipo": cfg["id"], "momento": iso(t), "en_vivo": momento is None, "valores": valores, "enlace": enlace}


@app.get("/api/e/{equipo}/diagnostico")
def diagnostico(equipo: str, momento: str | None = None):
    cfg = eq(equipo)
    try:
        return _diagnostico(cfg, momento)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


@app.get("/api/e/{equipo}/historial")
def historial(equipo: str, variables: str, minutos: float = 30, inicio: str | None = None, fin: str | None = None,
              puntos: int = 300):
    cfg = eq(equipo)
    vs = [v for v in variables.split(",") if v][:12]
    t1 = parse_t(fin) or ahora()
    t0 = parse_t(inicio) or (t1 - timedelta(minutes=minutos))
    paso = max(1, int((t1 - t0).total_seconds() / max(20, min(puntos, 1500))))
    filas = consulta(
        """SELECT variable, date_bin(make_interval(secs => %(p)s), time, %(t0)s) AS t, avg(valor) AS v
           FROM mediciones WHERE fuente = 'uns' AND variable = ANY(%(vs)s) AND time >= %(t0)s AND time < %(t1)s
           GROUP BY 1, 2 ORDER BY 1, 2""", {"p": paso, "t0": t0, "t1": t1, "vs": [largo(cfg, v) for v in vs]})
    series: dict[str, list] = {v: [] for v in vs}
    for f in filas:
        series[corto(cfg, f["variable"])].append([iso(f["t"]), round(f["v"], 3)])
    return {"inicio": iso(t0), "fin": iso(t1), "paso_s": paso, "series": series}


@app.get("/api/e/{equipo}/eventos")
def eventos(equipo: str, inicio: str | None = None, fin: str | None = None, horas: float = 4):
    """Cambios de estado (los definidos en 'eventos' del registro) para marcar la linea de tiempo."""
    cfg = eq(equipo)
    vs = [largo(cfg, v) for v in cfg.get("eventos", {})]
    if not vs:
        return []
    t1 = parse_t(fin) or ahora()
    t0 = parse_t(inicio) or (t1 - timedelta(hours=horas))
    filas = consulta(
        """SELECT variable, time, valor FROM (
             SELECT variable, time, valor, lag(valor) OVER (PARTITION BY variable ORDER BY time) AS prev
             FROM mediciones WHERE fuente = 'uns' AND time BETWEEN %(t0)s AND %(t1)s AND variable = ANY(%(vs)s)) x
           WHERE prev IS DISTINCT FROM valor AND prev IS NOT NULL ORDER BY time""", {"t0": t0, "t1": t1, "vs": vs})
    return [{"variable": corto(cfg, f["variable"]), "t": iso(f["time"]), "valor": f["valor"]} for f in filas]


@app.websocket("/ws/vivo/{equipo}")
async def ws_vivo(ws: WebSocket, equipo: str):
    if equipo not in EQUIPOS:
        await ws.close(code=4404)
        return
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    vivo.clientes[q] = equipo
    try:
        await ws.send_json({"tipo": "snapshot", **await asyncio.to_thread(estado, equipo)})
        while True:
            ev = await q.get()
            await ws.send_json(ev)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        vivo.clientes.pop(q, None)


# ----------------------------------------------------------------------------- agente (LLM + MCP de todos los equipos)
def _sistema_extra(equipo: str | None) -> str:
    lista = "\n".join(f"- {e['nombre']} {e['codigo']} (prefijo de herramientas '{e['alias']}__'): PLC {e['plc']}"
                      for e in REG["equipos"] if e["id"] in MODULOS)
    if equipo and equipo in EQUIPOS:
        e = EQUIPOS[equipo]
        contexto = (f"El usuario esta viendo el equipo {e['nombre']} ({e['codigo']}). Si la pregunta no nombra otro "
                    f"equipo, se refiere a este: usa las herramientas '{e['alias']}__'.")
    else:
        contexto = ("El usuario esta en la VISTA GENERAL del laboratorio. Si la pregunta abarca varios equipos "
                    "(estado general, alarmas, cual rinde peor...), consulta a cada uno con sus herramientas y "
                    "compara; responde con una linea por equipo y luego la conclusion.")
    return f"""Respondes dentro del lienzo de supervision del Laboratorio de Automatizacion USS. Equipos integrados:
{lista}
Cada herramienta lleva el prefijo del equipo al que consulta; nunca mezcles datos de un equipo con otro.
{contexto}
Escribe en espanol, breve y concreto: primero la conclusion con su numero y unidad, luego la evidencia. Usa siempre las
herramientas antes de afirmar algo del proceso. Todo es de solo lectura: no puedes cambiar setpoints ni arrancar o
parar equipos."""


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
    equipo_ctx = cuerpo.get("equipo") or None
    historial_chat = [m for m in cuerpo.get("mensajes", []) if m.get("role") in ("user", "assistant")
                      and isinstance(m.get("content"), str) and m["content"].strip()][-12:]
    if not historial_chat or historial_chat[-1]["role"] != "user":
        raise HTTPException(400, "El ultimo mensaje debe ser del usuario")
    if not os.getenv(CFG["clave"]):
        raise HTTPException(503, f"Falta {CFG['clave']} en el archivo .env del historiador")
    por_alias = {e["alias"]: e for e in REG["equipos"] if e["id"] in MODULOS}

    async def flujo():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        try:
            async with AsyncExitStack() as pila:
                sesiones: dict[str, Any] = {}
                tools: list[tuple[str, Any]] = []
                instrucciones: list[str] = []
                for alias, e in por_alias.items():
                    params = StdioServerParameters(command=sys.executable, args=[str(MCP_DIR / e["mcp_script"])],
                                                   env={**os.environ, "MCP_DSN": DB_DSN})
                    r, w = await pila.enter_async_context(stdio_client(params))
                    s = await pila.enter_async_context(ClientSession(r, w))
                    init = await s.initialize()
                    sesiones[alias] = s
                    tools += [(alias, t) for t in (await s.list_tools()).tools]
                    instrucciones.append(f"### {e['nombre']} {e['codigo']} (herramientas '{alias}__')\n"
                                         f"{init.instructions or ''}")
                yield _sse({"tipo": "inicio", "modelo": MODELO, "proveedor": CFG["nombre"], "herramientas": len(tools),
                            "equipos": list(por_alias)})
                sistema = "\n\n".join(instrucciones) + "\n\n" + _sistema_extra(equipo_ctx)

                def nombre_llm(alias: str, t) -> str:
                    return f"{alias}__{t.name}"

                def descripcion(alias: str, t) -> str:
                    e = por_alias[alias]
                    return f"[{e['nombre']} {e['codigo']}] {t.description or ''}"

                async def ejecutar(uid: str, nombre: str, entrada: dict):
                    """Llama la herramienta MCP del equipo; devuelve (evento SSE, texto para el modelo, es_error)."""
                    alias, _, herramienta = nombre.partition("__")
                    if alias not in sesiones or not herramienta:
                        msg = f"Herramienta desconocida: {nombre}"
                        return (_sse({"tipo": "resultado", "id": uid, "nombre": nombre, "ms": 0, "error": True,
                                      "datos": None}), msg, True)
                    t0 = asyncio.get_running_loop().time()
                    res = await sesiones[alias].call_tool(herramienta, entrada)
                    texto = "".join(getattr(c, "text", "") for c in res.content)
                    ms = round((asyncio.get_running_loop().time() - t0) * 1000)
                    try:
                        datos = json.loads(texto)
                    except json.JSONDecodeError:
                        datos = None
                    return (_sse({"tipo": "resultado", "id": uid, "nombre": nombre, "equipo": por_alias[alias]["id"],
                                  "ms": ms, "error": bool(res.is_error), "datos": datos}), texto, bool(res.is_error))

                def ev_herramienta(uid: str, nombre: str, entrada: dict) -> str:
                    alias = nombre.partition("__")[0]
                    return _sse({"tipo": "herramienta", "id": uid, "nombre": nombre, "entrada": entrada,
                                 "equipo": por_alias.get(alias, {}).get("id")})

                if PROVEEDOR == "anthropic":
                    import anthropic
                    cliente = anthropic.AsyncAnthropic()
                    herramientas = [{"name": nombre_llm(a, t), "description": descripcion(a, t),
                                     "input_schema": t.input_schema} for a, t in tools]
                    msgs: list[dict[str, Any]] = [dict(m) for m in historial_chat]
                    for _ in range(10):
                        async with cliente.messages.stream(model=MODELO, max_tokens=1800, system=sistema,
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
                            yield ev_herramienta(u.id, u.name, u.input)
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
                        "name": nombre_llm(a, t), "description": descripcion(a, t)[:1000],
                        "parameters": _esquema_compatible(t.input_schema)}} for a, t in tools]
                    msgs = [{"role": "system", "content": sistema}] + [dict(m) for m in historial_chat]
                    for _ in range(10):
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
                            yield ev_herramienta(c.id, c.function.name, entrada)
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
