"""Rutas del agente de supervisión y del catálogo MCP."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..modelos import AgentAskRequest

router = APIRouter(prefix="/api", tags=["agentes"])

#: Herramientas deterministas que expone el agente de supervisión.
HERRAMIENTAS = [
    {"name": "estado_planta", "server": "tiempo-real",
     "description": "Devuelve el estado ONLINE/OFFLINE y el valor actual de los equipos de la planta."},
    {"name": "leer_equipo", "server": "tiempo-real",
     "description": "Lee valor, consigna, desviación y alarma de un equipo concreto."},
    {"name": "verificar_alarma", "server": "tiempo-real",
     "description": "Lista las alarmas activas de la planta y del tanque."},
    {"name": "resumen_historico", "server": "histórico",
     "description": "Calcula mínimo, promedio y máximo de una variable en el búfer de historial."},
    {"name": "estado_plc", "server": "tiempo-real",
     "description": "Reporta la comunicación con el PLC 192.168.114.9 (MicroLogix 1100)."},
]


def _ctx(request: Request):
    return request.app.state.ctx


@router.get("/agent/tools")
async def herramientas() -> list[dict]:
    return HERRAMIENTAS


@router.get("/agent/status")
async def estado(request: Request) -> dict:
    ctx = _ctx(request)
    datos = ctx.agente.status()
    datos["multiagente"] = await ctx.agente.multi.en_linea()
    return datos


@router.post("/agent/ask")
async def preguntar(request: Request, solicitud: AgentAskRequest):
    ctx = _ctx(request)
    sesion = getattr(request.state, "sesion", None)
    usuario = sesion.usuario if sesion else None

    respuesta = await ctx.agente.preguntar(
        solicitud.message, solicitud.history, solicitud.model, usuario,
    )

    id_conversacion = ctx.agente.chats.registrar(
        solicitud.conversacion_id, solicitud.origen,
        (solicitud.message or "").strip(), respuesta, usuario,
    )
    respuesta["conversacionId"] = id_conversacion
    return respuesta


def _ve_todos(request: Request) -> bool:
    """Supervisor y admin ven todos los chats (evidencia de la tesis)."""
    ctx = _ctx(request)
    if not ctx.cfg.auth.habilitado:
        return True
    sesion = getattr(request.state, "sesion", None)
    return bool(sesion) and _al_menos(sesion.rol, "supervisor")


def _al_menos(rol: str | None, minimo: str) -> bool:
    escala = {"viewer": 1, "operador": 2, "supervisor": 3, "admin": 4}
    return escala.get((rol or "").lower(), 0) >= escala.get(minimo.lower(), 0)


@router.get("/agent/conversaciones")
async def conversaciones(request: Request) -> list[dict]:
    ctx = _ctx(request)
    sesion = getattr(request.state, "sesion", None)
    usuario = None
    if not _ve_todos(request):
        usuario = sesion.usuario if sesion else "-"
    return ctx.agente.chats.listar(usuario)


@router.get("/agent/conversaciones/{conversacion_id}")
async def conversacion(conversacion_id: str, request: Request):
    ctx = _ctx(request)
    sesion = getattr(request.state, "sesion", None)
    datos = ctx.agente.chats.leer(conversacion_id)
    if datos is None:
        return JSONResponse(status_code=404, content={"error": "CONVERSACION_NO_ENCONTRADA"})
    if not _ve_todos(request) and datos.get("usuario") != (sesion.usuario if sesion else None):
        return JSONResponse(status_code=404, content={"error": "CONVERSACION_NO_ENCONTRADA"})
    return datos


@router.get("/mcp/catalogo")
async def catalogo_mcp(request: Request) -> dict:
    """Servidores MCP reales del sistema multiagente (catálogo retenido)."""
    ctx = _ctx(request)
    en_linea = await ctx.agente.multi.en_linea()
    catalogo = await ctx.agente.multi.catalogo()
    return {"disponible": bool(en_linea and catalogo), "catalogo": catalogo}
