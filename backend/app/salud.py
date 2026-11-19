"""Estado de readiness del backend.

``/health/live``   el proceso responde (no depende de nada externo).
``/health/ready``  API activa + Mosquitto accesible + base de datos SOLO si está
                   habilitada (``Health:DatabaseEnabled``).

El PLC NUNCA es requisito de arranque: se reporta como dependencia industrial
degradada.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


async def _probar_tcp(host: str, puerto: int, timeout: float = 2.0) -> tuple[bool, str]:
    """Prueba de conexión TCP (sin librerías de terceros)."""
    try:
        fut = asyncio.open_connection(host, puerto)
        lector, escritor = await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return False, "timeout"
    except OSError as exc:
        return False, exc.strerror or str(exc)
    escritor.close()
    try:
        await escritor.wait_closed()
    except OSError:                       # pragma: no cover
        pass
    return True, "ok"


async def readiness(ctx) -> JSONResponse:
    cfg = ctx.cfg

    mqtt_ok, mqtt_det = await _probar_tcp(cfg.mqtt.host, cfg.mqtt.port)

    db_habilitada = cfg.health.database_enabled
    db_ok, db_det = True, "deshabilitada"
    if db_habilitada:
        db_ok, db_det = await _probar_tcp(cfg.health.database_host, cfg.health.database_port)

    nivel = ctx.estados.get("nivel-mcn09")
    plc_ok = bool(nivel and nivel.plc_conectado)

    listo = mqtt_ok and db_ok
    ahora = datetime.now().astimezone()
    cuerpo = {
        "status": "ready" if listo else "degraded",
        "checks": {
            "api": True,
            "mqtt": {"ok": mqtt_ok, "detalle": mqtt_det},
            "database": {"habilitada": db_habilitada, "ok": db_ok, "detalle": db_det},
        },
        # El PLC no bloquea el arranque: es una dependencia industrial.
        "dependenciaIndustrial": {
            "plc": "CONECTADO" if plc_ok else "DEGRADADA",
            "detalle": "no es requisito de arranque",
        },
        "modoControl": "AGENTES-SOLO-LECTURA" if cfg.agents_only else cfg.control.modo,
        "ts": ahora.isoformat(),
    }
    return JSONResponse(status_code=200 if listo else 503, content=cuerpo)
