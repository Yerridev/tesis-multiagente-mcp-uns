"""Punto de entrada del backend (FastAPI).

Sustituye al `Program.cs` de ASP.NET Core.  Mantiene:

* la misma URL base (``/api/...``) y los mismos códigos HTTP;
* la puerta de sesión (todo ``/api`` exige token salvo login/estado/health);
* el formato de error ``{"error": ...}``;
* el servicio de la SPA compilada en el mismo origen.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

# --- Windows: psycopg (async) no funciona con el ProactorEventLoop (el que
#     usa asyncio por defecto en Windows).  Hay que forzar el Selector.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:                    # pragma: no cover - Python >= 3.14
        pass

from .config import Config, config                       # noqa: E402
from .errores import registrar_manejadores               # noqa: E402
from .stream.canal import CanalSSE, generar_stream       # noqa: E402

log = logging.getLogger("mcp-industrial")

#: Rutas públicas: se consultan antes de tener sesión.
RUTAS_PUBLICAS = ("/api/health", "/api/auth/login", "/api/auth/estado")

#: Prefijos con StreamingResponse (no se deben cachear).
SIN_CACHE = (".html", ".js", ".css", ".svg")


class Contexto:
    """Estado de la aplicación (una sola instancia por proceso)."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.canal = CanalSSE()
        self.seguridad = None            # app.seguridad.SeguridadStore (F4)
        self.estados: dict[str, object] = {}
        self.planta = None               # app.estado.planta.PlantState (F3)
        self.control = None              # app.control.servicio.ControlService (F5)
        self.contratos_modulo: list = []  # caudal / presión / temperatura (F5)
        self.agente = None               # app.agentes.servicio (F6)
        self.tareas: list = []


def _raiz_wwwroot(cfg: Config) -> Path:
    """Carpeta con la SPA compilada."""
    candidatas = [cfg.ruta_wwwroot, Path(__file__).resolve().parents[2] / "frontend" / "dist"]
    for ruta in candidatas:
        if (ruta / "index.html").is_file():
            return ruta
    return candidatas[0]


@asynccontextmanager
async def _ciclo(app: FastAPI) -> AsyncIterator[None]:
    ctx: Contexto = app.state.ctx
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
    )
    log.info("MCP Industrial API (Python) · modo=%s · planta=%s",
             "AGENTES-SOLO-LECTURA" if ctx.cfg.agents_only else ctx.cfg.control.modo,
             ctx.cfg.planta_modo)
    await _arrancar(ctx)
    try:
        yield
    finally:
        await _detener(ctx)


async def _arrancar(ctx: Contexto) -> None:
    """Arranca los servicios en segundo plano (MQTT, difusión, control)."""
    from .arranque import arrancar

    await arrancar(ctx)


async def _detener(ctx: Contexto) -> None:
    from .arranque import detener

    await detener(ctx)


def crear_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or config()
    app = FastAPI(
        title="MCP Industrial API",
        version="2.0.0 (Python)",
        description="Backend de supervisión y control remoto del laboratorio UNS · MCP industrial.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=_ciclo,
    )
    app.state.ctx = Contexto(cfg)

    registrar_manejadores(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _puerta_de_sesion(request: Request, call_next):
        """Todo ``/api`` exige sesión válida salvo login, estado y health.

        401 = sesión inválida (el navegador vuelve al login).
        403 = sesión válida pero sin permiso (la interfaz solo muestra el error).
        """
        ctx: Contexto = request.app.state.ctx
        ruta = request.url.path
        if not ctx.cfg.auth.habilitado or not ruta.startswith("/api"):
            return await call_next(request)
        if any(ruta == p or ruta.startswith(p + "/") for p in RUTAS_PUBLICAS):
            return await call_next(request)

        if ctx.seguridad is None or not ctx.seguridad.listo:
            return JSONResponse(
                status_code=503,
                content={"error": "SEGURIDAD_NO_DISPONIBLE",
                         "detalle": getattr(ctx.seguridad, "error_inicio", None)},
            )

        token = _token_de(request)
        sesion = await ctx.seguridad.validar(token) if token else None
        if sesion is None:
            return JSONResponse(status_code=401, content={"error": "SESION_INVALIDA"})

        request.state.sesion = sesion
        request.state.token = token
        return await call_next(request)

    # ------------------------------------------------------------------ salud
    @app.get("/health/live", include_in_schema=False)
    async def health_live() -> dict:
        return {"status": "live", "ts": _ahora()}

    @app.get("/health/ready", include_in_schema=False)
    async def health_ready(request: Request) -> Response:
        from .salud import readiness

        return await readiness(request.app.state.ctx)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "healthy", "service": "MCP Industrial API", "timestamp": _ahora()}

    # ------------------------------------------------------------------ stream SSE
    app.get("/api/stream", include_in_schema=False)(stream)

    # ------------------------------------------------------------------ routers
    from .rutas import registrar_rutas

    registrar_rutas(app)

    # ------------------------------------------------------------------ SPA
    _montar_spa(app, _raiz_wwwroot(cfg))
    return app


async def stream(request: Request) -> Response:
    """Canal de telemetría en vivo (SSE). Sustituye al hub SignalR.

    El navegador lo abre con ``EventSource('/api/stream')``.  Como
    ``EventSource`` no puede mandar cabeceras, el token de sesión viaja en el
    query ``?access_token=``.
    """
    ctx: Contexto = request.app.state.ctx
    cola = await ctx.canal.suscribir()
    log.info("Cliente SSE conectado (%d en total)", ctx.canal.clientes)

    async def _cuerpo() -> AsyncIterator[bytes]:
        try:
            async for trozo in generar_stream(cola):
                yield trozo
        finally:
            await ctx.canal.desuscribir(cola)
            log.info("Cliente SSE desconectado (%d en total)", ctx.canal.clientes)

    return StreamingResponse(
        _cuerpo(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # nginx: no bufferizar (SSE)
        },
    )


def _token_de(request: Request) -> str | None:
    cabecera = request.headers.get("authorization", "")
    if cabecera.lower().startswith("bearer "):
        token = cabecera[7:].strip()
        if token:
            return token
    return request.query_params.get("access_token") or None


def _montar_spa(app: FastAPI, raiz: Path) -> None:
    """Sirve la SPA compilada y devuelve index.html para las rutas del cliente."""
    if not (raiz / "index.html").is_file():
        log.warning("No hay SPA compilada en %s (se espera 'npm run build')", raiz)
        return

    assets = raiz / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    def _enviar(camino: str) -> Response:
        destino = (raiz / camino).resolve()
        try:
            destino.relative_to(raiz.resolve())
        except ValueError:
            destino = raiz / "index.html"
        if not destino.is_file():
            destino = raiz / "index.html"
        tipo, _ = mimetypes.guess_type(str(destino))
        respuesta = FileResponse(destino, media_type=tipo or "application/octet-stream")
        if destino.suffix.lower() in SIN_CACHE:
            respuesta.headers["Cache-Control"] = "no-cache"
        return respuesta

    @app.get("/", include_in_schema=False)
    async def raiz_app() -> Response:
        return _enviar("index.html")

    @app.get("/{ruta:path}", include_in_schema=False)
    async def spa(ruta: str) -> Response:
        return _enviar(ruta)


def _ahora():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


app = crear_app()
