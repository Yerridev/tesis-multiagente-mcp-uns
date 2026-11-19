"""Rutas de la planta: equipos, señales, historial y latencia."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..modelos import EquipmentState, HistorySample, LevelDetail, SenalesModulo
from ..modulos import MODULOS, NIVEL

router = APIRouter(prefix="/api", tags=["planta"])


def _ctx(request: Request):
    return request.app.state.ctx


@router.get("/equipment", response_model=list[EquipmentState])
async def equipment(request: Request) -> list[EquipmentState]:
    """Estado de supervisión de los cuatro equipos (solo lectura)."""
    ctx = _ctx(request)
    ctx.planta.aplicar()
    return ctx.planta.todos()


@router.get("/equipment/{equipo_id}/signals", response_model=SenalesModulo)
async def senales(equipo_id: str, request: Request) -> SenalesModulo:
    """Señales crudas del módulo (UNS vía MQTT)."""
    ctx = _ctx(request)
    estado = ctx.estados.get(equipo_id)
    if estado is None:
        from ..errores import ErrorApi

        raise ErrorApi("EQUIPO_DESCONOCIDO", 404, equipo=equipo_id)
    return SenalesModulo(**estado.snapshot())


@router.get("/equipment/nivel-mcn09/detail", response_model=LevelDetail)
async def detalle_nivel(request: Request) -> LevelDetail:
    """Detalle del tanque MCN-09 (solo datos reales)."""
    ctx = _ctx(request)
    return LevelDetail(**ctx.planta.detalle_nivel())


@router.get("/equipment/{equipo_id}", response_model=EquipmentState)
async def equipment_id(equipo_id: str, request: Request) -> EquipmentState:
    ctx = _ctx(request)
    item = ctx.planta.obtener(equipo_id)
    if item is None:
        from ..errores import ErrorApi

        raise ErrorApi("EQUIPO_DESCONOCIDO", 404, equipo=equipo_id)
    return EquipmentState(**item)


@router.get("/history", response_model=list[HistorySample])
async def historial(request: Request, equipmentId: str | None = None,
                    limit: int = 300) -> list[HistorySample]:
    """Historial en memoria del backend (~30 min por equipo)."""
    ctx = _ctx(request)
    return [HistorySample(**m) for m in ctx.planta.historial(equipmentId, limit)]


@router.get("/latencia")
async def latencia(request: Request, muestras: bool = False) -> dict:
    """Latencia PLC → backend (indicador VD-03)."""
    from ..estado.latencia import resumen

    return resumen(muestras)


@router.post("/latencia/reiniciar")
async def latencia_reiniciar() -> dict:
    from ..estado.latencia import reiniciar

    reiniciar()
    return {"ok": True}
