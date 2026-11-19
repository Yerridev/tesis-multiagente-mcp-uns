"""Contratos de control por módulo (caudal, presión, temperatura)."""

from __future__ import annotations

from .base import ControlModulo
from .caudal import CaudalControl
from .presion import PresionControl
from .temperatura import TemperaturaControl

__all__ = ["ControlModulo", "CaudalControl", "PresionControl", "TemperaturaControl",
           "construir_contratos"]


def construir_contratos(ctx) -> list[ControlModulo]:
    """Instancia los tres contratos con sus opciones de configuración."""
    return [CaudalControl(ctx), PresionControl(ctx), TemperaturaControl(ctx)]
