"""Errores de la API.

El frontend lee siempre ``datos.error`` (nunca ``detail``), así que TODA
respuesta de error debe serializarse como ``{"error": "<codigo>"}`` con las
claves extra que haga falta.  Se sustituye el ``{"detail": ...}`` por defecto
de FastAPI para no romper la interfaz.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorApi(Exception):
    """Error de negocio con código estable y código HTTP."""

    def __init__(self, codigo: str, http: int = 400, **extra: Any) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.http = http
        self.extra = extra


def _respuesta(codigo: str, http: int, extra: dict[str, Any] | None = None) -> JSONResponse:
    cuerpo: dict[str, Any] = {"error": codigo}
    if extra:
        cuerpo.update(extra)
    return JSONResponse(status_code=http, content=cuerpo)


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorApi)
    async def _error_api(_: Request, exc: ErrorApi) -> JSONResponse:
        return _respuesta(exc.codigo, exc.http, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 400 y no 422: el frontend solo sabe leer {"error": ...}.
        return _respuesta(
            "PETICION_INVALIDA",
            400,
            {"detalle": _resumen_validacion(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo = _codigo_http(exc.status_code)
        detalle = exc.detail if isinstance(exc.detail, str) else None
        return _respuesta(codigo, exc.status_code, {"detalle": detalle} if detalle else None)

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        return _respuesta("ERROR_INTERNO", 500, {"detalle": str(exc)[:300]})


def _codigo_http(status: int) -> str:
    return {
        400: "PETICION_INVALIDA",
        401: "SESION_INVALIDA",
        403: "PERMISO_INSUFICIENTE",
        404: "NO_ENCONTRADO",
        409: "CONFLICTO",
        429: "DEMASIADOS_INTENTOS",
        503: "NO_DISPONIBLE",
    }.get(status, "ERROR")


def _resumen_validacion(exc: RequestValidationError) -> str:
    partes = []
    for error in exc.errors():
        campo = ".".join(str(c) for c in error.get("loc", ())[1:]) or "cuerpo"
        partes.append(f"{campo}: {error.get('msg', 'inválido')}")
    return "; ".join(partes)[:300]
