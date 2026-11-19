"""Rutas de control remoto.

Equivale a las rutas ``/api/control/*`` del backend ASP.NET.

Autenticación: con la autenticación habilitada vale la sesión (la exige la
puerta global de ``/api``).  Sin ella se acepta la clave de desarrollo
``Bearer dev-viewer|dev-operador|dev-supervisor|dev-admin``, cuya tabla se
vacía en cuanto hay usuarios reales.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..modelos import SolicitudComando

router = APIRouter(prefix="/api/control", tags=["control"])


def _ctx(request: Request):
    return request.app.state.ctx


def _autenticar(request: Request, rol_minimo: str | None = None):
    """Devuelve (rol, usuario, respuesta_de_error)."""
    ctx = _ctx(request)
    sesion = getattr(request.state, "sesion", None)
    if sesion is not None:
        if rol_minimo is not None and not _al_menos(sesion.rol, rol_minimo):
            return None, None, JSONResponse(status_code=403, content={
                "error": "PERMISO_INSUFICIENTE", "requiere": rol_minimo})
        return sesion.rol, sesion.usuario, None

    cabecera = request.headers.get("authorization", "")
    if not cabecera.strip():
        return None, None, JSONResponse(status_code=401, content={"error": "SIN_AUTENTICACION"})
    if not cabecera.lower().startswith("bearer "):
        return None, None, JSONResponse(status_code=401, content={"error": "SIN_AUTENTICACION"})
    clave = cabecera[7:].strip()
    for usuario, rol in ctx.cfg.control.usuarios.items():
        if usuario == clave:
            if rol_minimo is not None and not _al_menos(rol, rol_minimo):
                return None, None, JSONResponse(status_code=403, content={
                    "error": "PERMISO_INSUFICIENTE", "requiere": rol_minimo})
            return rol, usuario, None
    return None, None, JSONResponse(status_code=401, content={"error": "SIN_AUTENTICACION"})


def _al_menos(rol: str | None, minimo: str) -> bool:
    escala = {"viewer": 1, "operador": 2, "supervisor": 3, "admin": 4}
    return escala.get((rol or "").lower(), 0) >= escala.get(minimo.lower(), 0)


def _sin_control(ctx) -> JSONResponse | None:
    """En modo AGENTS_ONLY no hay servicio de control."""
    if ctx.cfg.agents_only:
        return JSONResponse(status_code=404, content={"error": "CONTROL_NO_DISPONIBLE"})
    return None


# ============================================================ nivel (MCN-09)
@router.get("/contrato")
async def contrato(request: Request):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    return ctx.control.contrato_publico()


@router.get("/estado")
async def estado(request: Request):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    _, usuario, fallo = _autenticar(request)
    if fallo is not None:
        return fallo
    return {"usuario": usuario, "datos": ctx.control.estado_publico()}


@router.post("/nivel/comandos")
async def nivel_comando(request: Request, solicitud: SolicitudComando):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    rol, usuario, fallo = _autenticar(request)
    if fallo is not None:
        return fallo
    codigo, orden, error = await ctx.control.enviar(solicitud, usuario or "desconocido",
                                                     rol or "viewer")
    if orden is not None:
        return JSONResponse(status_code=codigo, content=orden.para_senal())
    return JSONResponse(status_code=codigo, content={"error": error})


@router.get("/nivel/comandos")
async def nivel_comandos(request: Request, limit: int = 10):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    _, _, fallo = _autenticar(request)
    if fallo is not None:
        return fallo
    return [o.para_senal() for o in ctx.control.ultimas(limit)]


@router.get("/nivel/comandos/{orden_id}")
async def nivel_comando_id(orden_id: str, request: Request):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    _, _, fallo = _autenticar(request)
    if fallo is not None:
        return fallo
    orden = ctx.control.obtener(orden_id)
    if orden is None:
        return JSONResponse(status_code=404, content={"error": "ORDEN_NO_ENCONTRADA"})
    return orden.para_senal()


@router.get("/auditoria")
async def auditoria(request: Request, limit: int = 50):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    _, _, fallo = _autenticar(request, "supervisor")
    if fallo is not None:
        return fallo
    return ctx.control.auditoria.ultimas(limit)


# ============================================================ caudal / presión / temperatura
def _contrato_modulo(ctx, clave: str):
    for contrato in ctx.contratos_modulo:
        if contrato.clave == clave:
            return contrato
    return None


@router.get("/caudal/estado")
async def caudal_estado(request: Request):
    return await _estado_modulo(request, "caudal")


@router.post("/caudal/comandos")
async def caudal_comando(request: Request, solicitud: SolicitudComando):
    return await _comando_modulo(request, "caudal", solicitud)


@router.get("/caudal/comandos")
async def caudal_comandos(request: Request, limit: int = 10):
    return await _comandos_modulo(request, "caudal", limit)


@router.get("/presion/estado")
async def presion_estado(request: Request):
    return await _estado_modulo(request, "presion")


@router.post("/presion/comandos")
async def presion_comando(request: Request, solicitud: SolicitudComando):
    return await _comando_modulo(request, "presion", solicitud)


@router.get("/presion/comandos")
async def presion_comandos(request: Request, limit: int = 10):
    return await _comandos_modulo(request, "presion", limit)


@router.get("/temperatura/estado")
async def temperatura_estado(request: Request):
    return await _estado_modulo(request, "temperatura")


@router.post("/temperatura/comandos")
async def temperatura_comando(request: Request, solicitud: SolicitudComando):
    return await _comando_modulo(request, "temperatura", solicitud)


@router.get("/temperatura/comandos")
async def temperatura_comandos(request: Request, limit: int = 10):
    return await _comandos_modulo(request, "temperatura", limit)


async def _estado_modulo(request: Request, clave: str):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    _, usuario, fallo = _autenticar(request)
    if fallo is not None:
        return fallo
    contrato = _contrato_modulo(ctx, clave)
    if contrato is None:                      # pragma: no cover
        return JSONResponse(status_code=404, content={"error": "MODULO_DESCONOCIDO"})
    return {"usuario": usuario, "datos": contrato.estado_publico()}


async def _comando_modulo(request: Request, clave: str, solicitud: SolicitudComando):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    rol, usuario, fallo = _autenticar(request)
    if fallo is not None:
        return fallo
    contrato = _contrato_modulo(ctx, clave)
    if contrato is None:                      # pragma: no cover
        return JSONResponse(status_code=404, content={"error": "MODULO_DESCONOCIDO"})
    codigo, orden, error = await contrato.enviar(solicitud, usuario or "desconocido",
                                                  rol or "viewer")
    if orden is not None:
        return JSONResponse(status_code=codigo, content=orden.para_senal())
    return JSONResponse(status_code=codigo, content={"error": error})


async def _comandos_modulo(request: Request, clave: str, limit: int):
    ctx = _ctx(request)
    bloqueo = _sin_control(ctx)
    if bloqueo is not None:
        return bloqueo
    _, _, fallo = _autenticar(request)
    if fallo is not None:
        return fallo
    contrato = _contrato_modulo(ctx, clave)
    if contrato is None:                      # pragma: no cover
        return JSONResponse(status_code=404, content={"error": "MODULO_DESCONOCIDO"})
    return contrato.ultimas(limit)
