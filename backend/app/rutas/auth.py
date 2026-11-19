"""Rutas de autenticación y gestión de usuarios."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..modelos import (
    AccesoFila,
    EstadoAuth,
    RespuestaLogin,
    SolicitudLogin,
    SolicitudUsuario,
    UsuarioFila,
    YoModelo,
)

router = APIRouter(prefix="/api/auth", tags=["seguridad"])


def _ctx(request: Request):
    return request.app.state.ctx


def _ip_de(request: Request) -> str | None:
    """IP del cliente (respeta X-Forwarded-For del proxy)."""
    reenviada = request.headers.get("x-forwarded-for", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else None


def _sesion_de(request: Request):
    return getattr(request.state, "sesion", None)


def _solo_con_auth(request: Request):
    """409 si la autenticación está deshabilitada; None si se puede seguir."""
    ctx = _ctx(request)
    if not ctx.cfg.auth.habilitado:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"error": "AUTENTICACION_DESHABILITADA"})
    if ctx.seguridad is None or not ctx.seguridad.listo:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"error": "SEGURIDAD_NO_DISPONIBLE",
                     "detalle": getattr(ctx.seguridad, "error_inicio", None)},
        )
    return None


def _requiere(request: Request, rol_minimo: str):
    """None si tiene permiso; si no, la respuesta 401/403."""
    ctx = _ctx(request)
    if not ctx.cfg.auth.habilitado:
        return None
    sesion = _sesion_de(request)
    if sesion is None:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=401, content={"error": "SESION_INVALIDA"})
    if not _al_menos(sesion.rol, rol_minimo):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=403,
                            content={"error": "PERMISO_INSUFICIENTE", "requiere": rol_minimo})
    return None


def _al_menos(rol: str | None, minimo: str) -> bool:
    escala = {"viewer": 1, "operador": 2, "supervisor": 3, "admin": 4}
    return escala.get((rol or "").lower(), 0) >= escala.get(minimo.lower(), 0)


@router.get("/estado", response_model=EstadoAuth)
async def estado(request: Request) -> EstadoAuth:
    ctx = _ctx(request)
    return EstadoAuth(
        habilitado=ctx.cfg.auth.habilitado,
        listo=bool(ctx.seguridad and ctx.seguridad.listo),
        horas_sesion=ctx.cfg.auth.horas_sesion,
    )


@router.post("/login", response_model=RespuestaLogin)
async def login(request: Request, solicitud: SolicitudLogin):
    from fastapi.responses import JSONResponse

    ctx = _ctx(request)
    bloqueo = _solo_con_auth(request)
    if bloqueo is not None:
        return bloqueo

    sesion, token, error = await ctx.seguridad.login(
        solicitud.usuario, solicitud.password,
        _ip_de(request), request.headers.get("user-agent"),
    )
    if sesion is None or token is None:
        codigo = 429 if error == "DEMASIADOS_INTENTOS" else 401
        return JSONResponse(status_code=codigo, content={"error": error})
    return RespuestaLogin(token=token, usuario=sesion.usuario, nombre=sesion.nombre,
                          rol=sesion.rol, expira=sesion.expira)


@router.post("/logout")
async def logout(request: Request) -> dict:
    ctx = _ctx(request)
    sesion = _sesion_de(request)
    token = getattr(request.state, "token", None)
    if sesion is not None and token and sesion.usuario_id > 0:
        await ctx.seguridad.logout(token, sesion.usuario, _ip_de(request))
    return {"ok": True}


@router.get("/yo", response_model=YoModelo)
async def yo(request: Request) -> YoModelo:
    ctx = _ctx(request)
    sesion = _sesion_de(request)
    if sesion is None:
        return YoModelo(habilitado=False, usuario="local",
                        nombre="Sin autenticación", rol="admin")
    return YoModelo(habilitado=True, usuario=sesion.usuario, nombre=sesion.nombre,
                    rol=sesion.rol, expira=sesion.expira)


@router.get("/usuarios", response_model=list[UsuarioFila])
async def listar_usuarios(request: Request):
    from fastapi.responses import JSONResponse

    bloqueo = _solo_con_auth(request) or _requiere(request, "admin")
    if bloqueo is not None:
        return bloqueo
    ctx = _ctx(request)
    return [UsuarioFila(**u) for u in await ctx.seguridad.usuarios()]


@router.post("/usuarios")
async def crear_usuario(request: Request, solicitud: SolicitudUsuario):
    from fastapi.responses import JSONResponse

    bloqueo = _solo_con_auth(request) or _requiere(request, "admin")
    if bloqueo is not None:
        return bloqueo
    ctx = _ctx(request)
    actor = _sesion_de(request)
    error = await ctx.seguridad.crear(
        solicitud.usuario, solicitud.nombre, solicitud.rol, solicitud.password,
        actor.usuario if actor else "?", _ip_de(request),
    )
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    return {"ok": True}


@router.put("/usuarios/{usuario_id}")
async def actualizar_usuario(usuario_id: int, request: Request, solicitud: SolicitudUsuario):
    from fastapi.responses import JSONResponse

    bloqueo = _solo_con_auth(request) or _requiere(request, "admin")
    if bloqueo is not None:
        return bloqueo
    ctx = _ctx(request)
    actor = _sesion_de(request)
    if actor is None:
        return JSONResponse(status_code=401, content={"error": "SESION_INVALIDA"})
    password = solicitud.password or None
    error = await ctx.seguridad.actualizar(
        usuario_id, solicitud.nombre, solicitud.rol, solicitud.activo, password,
        actor, _ip_de(request),
    )
    if error:
        return JSONResponse(status_code=400, content={"error": error})
    return {"ok": True}


@router.get("/accesos", response_model=list[AccesoFila])
async def listar_accesos(request: Request, limit: int = 200):
    from fastapi.responses import JSONResponse

    bloqueo = _solo_con_auth(request) or _requiere(request, "admin")
    if bloqueo is not None:
        return bloqueo
    ctx = _ctx(request)
    return [AccesoFila(**a) for a in await ctx.seguridad.accesos(limit)]
