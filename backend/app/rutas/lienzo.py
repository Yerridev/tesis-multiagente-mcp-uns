"""Persistencia de las posiciones de los lienzos (nodos y lados de las flechas).

Archivo por módulo en ``Lienzo:Ruta`` (registros/lienzos en la PC).  Así las
posiciones se ven igual en cualquier navegador/PC y en el panel del sistema
multiagente.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["lienzo"])

ID_VALIDO = re.compile(r"^[a-z0-9-]{3,40}$")
MAX_CUERPO = 200_000


def _ruta_lienzos(ctx) -> Path:
    return Path(ctx.cfg.lienzo_ruta or (Path.cwd() / "registros" / "lienzos"))


@router.get("/lienzo/{lienzo_id}/layout")
async def leer_layout(lienzo_id: str, request: Request):
    from fastapi.responses import JSONResponse, Response

    if not ID_VALIDO.match(lienzo_id):
        return JSONResponse(status_code=400, content={"error": "ID_INVALIDO"})
    ctx = request.app.state.ctx
    archivo = _ruta_lienzos(ctx) / f"{lienzo_id}.json"
    if not archivo.is_file():
        return JSONResponse(status_code=404, content={"error": "LAYOUT_NO_ENCONTRADO"})
    return Response(archivo.read_text(encoding="utf-8"), media_type="application/json")


@router.put("/lienzo/{lienzo_id}/layout")
async def guardar_layout(lienzo_id: str, request: Request):
    from fastapi.responses import JSONResponse

    if not ID_VALIDO.match(lienzo_id):
        return JSONResponse(status_code=400, content={"error": "ID_INVALIDO"})
    cuerpo = (await request.body()).decode("utf-8", errors="replace")
    if len(cuerpo) > MAX_CUERPO:
        return JSONResponse(status_code=400, content={"error": "DEMASIADO_GRANDE"})
    try:
        json.loads(cuerpo)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "JSON_INVALIDO"})

    ctx = request.app.state.ctx
    carpeta = _ruta_lienzos(ctx)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{lienzo_id}.json").write_text(cuerpo, encoding="utf-8")
    return {"ok": True}
