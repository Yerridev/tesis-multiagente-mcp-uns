"""Control real protegido del MCT-09 (Twido): solo %M30 (marcha) y %MW100 (SP)."""

from __future__ import annotations

from typing import Any

from ...modelos import TipoComando
from ..contrato import Motivos
from .base import ControlModulo


class TemperaturaControl(ControlModulo):
    clave = "temperatura"
    equipo = "temp-mct09"
    unidad = "C"
    telemetria_max_segundos = 15
    evento_resultado = "temperaturaControlResultado"
    host_config = "temperatura_control_host"
    port_config = "temperatura_control_port"
    tipos_admitidos = frozenset({
        TipoComando.iniciar, TipoComando.detener, TipoComando.setpoint,
        TipoComando.parametro_pid,
    })

    def validar(self, solicitud, tipo: TipoComando) -> str | None:
        valor = solicitud.valor
        if tipo is TipoComando.setpoint:
            unidad = (solicitud.unidad or "").strip().lower()
            if unidad not in ("c", "°c"):
                return Motivos.UNIDAD_INVALIDA
            if valor is None or valor != valor or valor < 15 or valor > 50:
                return Motivos.RANGO_INVALIDO
        elif tipo is TipoComando.parametro_pid:
            if (solicitud.parametro or "").lower() not in ("kp", "ti", "td"):
                return Motivos.TIPO_DESCONOCIDO
            if (valor is None or valor != valor or valor < 0 or valor > 10000
                    or valor % 1 != 0):
                return Motivos.RANGO_INVALIDO
        elif tipo in (TipoComando.reiniciar, TipoComando.abrir_valvula,
                      TipoComando.cerrar_valvula, TipoComando.ajustar_valvula):
            return Motivos.TIPO_DESCONOCIDO
        return None

    def preflight(self, solicitud, tipo: TipoComando) -> str | None:
        if not self.real_armado():
            return Motivos.REAL_NO_ARMADO
        if not self.estado.plc_conectado:
            return Motivos.PLC_DESCONECTADO
        if self.estado.modo() != "PC":
            return Motivos.SELECTOR_NO_REMOTO
        if tipo is TipoComando.iniciar and (
            self.estado.booleano("falla/nivel_principal") is True
            or self.estado.booleano("falla/nivel_enfriador") is True
        ):
            return Motivos.NIVEL_BAJO_T1
        edad = self._edad_telemetria()
        if edad is None or edad > self.telemetria_max_segundos:
            return Motivos.TELEMETRIA_VENCIDA
        return None

    def proceso_publico(self) -> dict[str, Any]:
        return {
            "plc": "CONECTADO" if self.estado.plc_conectado else "DESCONECTADO",
            "selector": self.estado.modo(),
            "mqtt": self.estado.mqtt_conectado,
            "fallaPrincipal": self.estado.booleano("falla/nivel_principal"),
            "fallaEnfriador": self.estado.booleano("falla/nivel_enfriador"),
        }
