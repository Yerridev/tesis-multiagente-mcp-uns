"""Planta simulada: modo de operación y llaves manuales (V1..V7, VF).

En modo ``simulado`` las llaves manuales del mimico se mandan al simulador por
MQTT.  En modo ``real`` este endpoint rechaza: las llaves reales son de mano.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import APIRouter, Request

from ..modelos import SolicitudLlave
from ..modulos import MODULOS

router = APIRouter(prefix="/api", tags=["simulacion"])

LLAVE_VALIDA = re.compile(r"^(V[1-7]|VF)$")


def _ctx(request: Request):
    return request.app.state.ctx


def _bases() -> dict[str, str]:
    return {m.clave: m.base_mqtt for m in MODULOS}


@router.get("/planta/modo")
async def modo_planta(request: Request) -> dict:
    return {"modo": request.app.state.ctx.cfg.planta_modo}


async def _publicar(ctx, topico: str, cuerpo: str) -> bool:
    from ..mqtt.publicador import publicar

    host = ctx.cfg.mqtt.caudal_control_host or ctx.cfg.mqtt.host
    puerto = ctx.cfg.mqtt.caudal_control_port
    return await publicar(topico, cuerpo, host, puerto)


@router.post("/sim/llave")
async def sim_llave(request: Request, solicitud: SolicitudLlave):
    from ..errores import ErrorApi

    ctx = _ctx(request)
    _exigir_operador(request)

    if ctx.cfg.planta_modo != "simulado":
        raise ErrorApi("PLANTA_REAL: las llaves reales son manuales", 409)

    bases = _bases()
    base = bases.get((solicitud.modulo or "").lower())
    if base is None:
        raise ErrorApi("MODULO_DESCONOCIDO", 400)
    llave = (solicitud.id or "").strip().upper()
    if not LLAVE_VALIDA.match(llave):
        raise ErrorApi("LLAVE_DESCONOCIDA", 400)

    cuerpo = json.dumps({"id": llave, "abierta": solicitud.abierta,
                          "ts": datetime.now().astimezone().isoformat()})
    if not await _publicar(ctx, f"{base}/sim/cmd/llave", cuerpo):
        raise ErrorApi("MQTT_NO_DISPONIBLE", 503)
    return {"ok": True, "modulo": solicitud.modulo, "id": llave, "abierta": solicitud.abierta}


@router.post("/sim/reiniciar")
async def sim_reiniciar(request: Request, solicitud: SolicitudLlave):
    from ..errores import ErrorApi

    ctx = _ctx(request)
    _exigir_operador(request)

    if ctx.cfg.planta_modo != "simulado":
        raise ErrorApi("PLANTA_REAL", 409)

    base = _bases().get((solicitud.modulo or "").lower())
    if base is None:
        raise ErrorApi("MODULO_DESCONOCIDO", 400)
    if not await _publicar(ctx, f"{base}/sim/cmd/reiniciar", "{}"):
        raise ErrorApi("MQTT_NO_DISPONIBLE", 503)
    return {"ok": True}


def _exigir_operador(request: Request) -> None:
    """Requiere rol >= operador (si la autenticación está habilitada)."""
    from ..errores import ErrorApi

    ctx = request.app.state.ctx
    if not ctx.cfg.auth.habilitado:
        return
    sesion = getattr(request.state, "sesion", None)
    if sesion is None:
        raise ErrorApi("SESION_INVALIDA", 401)
    if not _al_menos(sesion.rol, "operador"):
        raise ErrorApi("PERMISO_INSUFICIENTE", 403, requiere="operador")


def _al_menos(rol: str | None, minimo: str) -> bool:
    escala = {"viewer": 1, "operador": 2, "supervisor": 3, "admin": 4}
    return escala.get((rol or "").lower(), 0) >= escala.get(minimo.lower(), 0)
