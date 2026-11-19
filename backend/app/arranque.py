"""Arranque y parada de los servicios en segundo plano.

Equivale a los ``BackgroundService`` de ASP.NET (NivelMqttService,
CaudalMqttService, ControlMqttService, PlantSimulator).  Cada servicio corre
como una tarea de asyncio y se cancela limpiamente al apagar.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def arrancar(ctx) -> None:
    """Levanta todos los servicios de fondo."""
    # --- seguridad (F4): usuarios y sesiones en TimescaleDB -------------------
    if ctx.cfg.auth.habilitado:
        from .seguridad.store import SeguridadStore

        ctx.seguridad = SeguridadStore(ctx.cfg.auth)
        ctx.tareas.append(asyncio.create_task(ctx.seguridad.inicializar(), name="seguridad"))

    # --- estados de telemetría (F3) ------------------------------------------
    from .estado.planta import PlantState
    from .estado.modulo import EstadoModulo
    from .modulos import MODULOS

    ctx.estados = {m.clave: EstadoModulo(m) for m in MODULOS}
    ctx.planta = PlantState(ctx.estados)
    for estado in ctx.estados.values():
        ctx.tareas.append(asyncio.create_task(estado.consumir(ctx), name=f"mqtt-{estado.clave}"))

    # --- control (F5) ----------------------------------------------------------
    if not ctx.cfg.agents_only:
        from .control.servicio import ControlService
        from .control.contratos import construir_contratos

        ctx.control = ControlService(ctx)
        ctx.tareas.append(asyncio.create_task(ctx.control.consumir(), name="control-mqtt"))
        ctx.contratos_modulo = construir_contratos(ctx)
        for contrato in ctx.contratos_modulo:
            ctx.tareas.append(asyncio.create_task(contrato.consumir(), name=f"control-{contrato.clave}"))

    # --- difusión de telemetría al canal SSE ----------------------------------
    ctx.tareas.append(asyncio.create_task(_difundir(ctx), name="difusion"))

    # --- agente (F6) -----------------------------------------------------------
    if not ctx.cfg.agents_only:
        from .agentes.servicio import AgenteService

        ctx.agente = AgenteService(ctx)
        ctx.tareas.append(asyncio.create_task(ctx.agente.arrancar(), name="agente"))

    log.info("Servicios de fondo arrancados: %d", len(ctx.tareas))


async def _difundir(ctx) -> None:
    """Empuja la telemetría al canal SSE una vez por segundo (como el hub)."""
    from .estado.planta import snapshot_planta

    while True:
        try:
            await asyncio.sleep(1.0)
            if ctx.planta is None:
                continue
            await ctx.canal.emitir("telemetry", snapshot_planta(ctx.planta))
            for clave, evento in (
                ("nivel-mcn09", "nivelSenales"),
                ("caudal-mcc09", "caudalSenales"),
                ("presion-mcp09", "presionSenales"),
                ("temp-mct09", "temperaturaSenales"),
            ):
                estado = ctx.estados.get(clave)
                if estado is not None:
                    await ctx.canal.emitir(evento, estado.snapshot())
        except asyncio.CancelledError:
            raise
        except Exception:                       # pragma: no cover
            log.exception("Fallo en la difusión de telemetría")
            await asyncio.sleep(1.0)


async def detener(ctx) -> None:
    """Cancela los servicios de fondo."""
    for tarea in ctx.tareas:
        tarea.cancel()
    if ctx.tareas:
        await asyncio.gather(*ctx.tareas, return_exceptions=True)
    ctx.tareas.clear()
    log.info("Servicios de fondo detenidos")
