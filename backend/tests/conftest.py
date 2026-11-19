"""Fixtures compartidas de las pruebas del backend."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ControlCfg, MqttCfg                      # noqa: E402
from app.estado.modulo import EstadoModulo                      # noqa: E402
from app.modulos import NIVEL                                   # noqa: E402


class CanalFalso:
    """Canal SSE de mentira: guarda lo que se emitiría."""

    def __init__(self) -> None:
        self.eventos: list[tuple[str, Any]] = []

    async def emitir(self, evento: str, datos: Any) -> None:
        self.eventos.append((evento, datos))


@dataclass
class CtxFalso:
    """Contexto mínimo para probar el servicio de control sin broker ni PLC."""

    cfg: Any
    estados: dict[str, EstadoModulo]
    canal: CanalFalso = field(default_factory=CanalFalso)
    contratos_modulo: list = field(default_factory=list)


class Reloj:
    """Reloj controlable para expirar/vencer órdenes en pruebas."""

    def __init__(self) -> None:
        self.actual = datetime.now().astimezone()

    def ahora(self) -> datetime:
        return self.actual

    def avanzar(self, delta: timedelta) -> None:
        self.actual += delta


@dataclass
class CfgFalso:
    control: ControlCfg
    mqtt: MqttCfg = field(default_factory=MqttCfg)
    agents_only: bool = False
    auth: Any = None


def _nivel_estado(plc: str = "CONECTADO", selector: str = "REMOTO",
                  nivel_bajo: bool = False, mqtt: bool = True,
                  fuente_control: str | None = "PC") -> EstadoModulo:
    estado = EstadoModulo(NIVEL)
    estado.mqtt_conectado = mqtt
    base = f"{NIVEL.base_mqtt}/funcional"
    estado.aplicar(f"{base}/plc/conexion", plc)
    estado.aplicar(f"{base}/estado/selector_remoto",
                   "true" if selector == "REMOTO" else "false")
    estado.aplicar(f"{base}/estado/selector_local",
                   "true" if selector == "LOCAL" else "false")
    if fuente_control is not None:
        estado.aplicar(f"{base}/estado/fuente_control", fuente_control)
    if nivel_bajo:
        estado.aplicar(f"{base}/estado/alarma_nivel_bajo_tanque1", "true")
    # Telemetría sana del sensor de nivel: N7:4 en media escala (no saturado) y el
    # flag explícito en false.  El conector edge publica ambos siempre.
    estado.aplicar(f"{base}/nivel/raw", '{"value":16548,"unit":"cuentas"}')
    estado.aplicar(f"{base}/nivel/fuera_rango_sensor", '{"value":false}')
    return estado


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def control_cfg() -> ControlCfg:
    return ControlCfg(
        modo="DryRun",
        habilitado_escritura=False,
        timeout_segundos=5,
        expiracion_segundos=15,
        ventana_duplicados_segundos=30,
        variable_entorno_real=None,
    )


@pytest.fixture
def crear_servicio(control_cfg, reloj):
    """Crea el ControlService con transporte en memoria y reloj controlable."""
    from app.control.servicio import ControlService

    publicados: list[str] = []

    async def _publicar(cuerpo: str) -> bool:
        publicados.append(cuerpo)
        return True

    def _crear(nivel: EstadoModulo | None = None, **ajustes):
        cfg = ControlCfg(**{**control_cfg.__dict__, **ajustes})
        ctx = CtxFalso(CfgFalso(control=cfg), {"nivel-mcn09": nivel or _nivel_estado()})
        servicio = ControlService(ctx, publicar=_publicar, ahora=reloj.ahora)
        return servicio, publicados

    return _crear
