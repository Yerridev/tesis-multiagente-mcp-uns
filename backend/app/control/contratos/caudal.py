"""Control del MCC-09 (S7-200). El lazo corre en el PLC; el SCADA escribe
consigna, apertura de válvula y parámetros del PID."""

from __future__ import annotations

from typing import Any

from ...modelos import TipoComando
from ..contrato import Motivos
from .base import ControlModulo


class CaudalControl(ControlModulo):
    clave = "caudal"
    equipo = "caudal-mcc09"
    unidad = "L/min"
    telemetria_max_segundos = 15
    evento_resultado = "caudalControlResultado"
    host_config = "caudal_control_host"
    port_config = "caudal_control_port"
    tipos_admitidos = frozenset({
        TipoComando.iniciar, TipoComando.detener, TipoComando.setpoint,
        TipoComando.ajustar_valvula, TipoComando.parametro_pid,
    })

    def validar(self, solicitud, tipo: TipoComando) -> str | None:
        valor = solicitud.valor

        def fuera(minimo: float, maximo: float) -> bool:
            return (valor is None or valor != valor or valor in (float("inf"), float("-inf"))
                    or valor < minimo or valor > maximo)

        if tipo is TipoComando.setpoint:
            if (solicitud.unidad or "").strip().lower() != self.unidad.lower():
                return Motivos.UNIDAD_INVALIDA
            if fuera(0, 140):
                return Motivos.RANGO_INVALIDO
        elif tipo is TipoComando.ajustar_valvula:
            if fuera(0, 100):
                return Motivos.RANGO_INVALIDO
        elif tipo is TipoComando.parametro_pid:
            parametro = (solicitud.parametro or "").lower()
            if parametro not in ("kc", "ti", "td"):
                return Motivos.TIPO_DESCONOCIDO
            maximo = 100 if parametro == "kc" else 600
            if fuera(0, maximo):
                return Motivos.RANGO_INVALIDO
        elif tipo in (TipoComando.reiniciar, TipoComando.abrir_valvula, TipoComando.cerrar_valvula):
            return Motivos.TIPO_DESCONOCIDO
        return None

    def preflight(self, solicitud, tipo: TipoComando) -> str | None:
        if not self.real_armado():
            return Motivos.REAL_NO_ARMADO
        if not self.estado.plc_conectado:
            return Motivos.PLC_DESCONECTADO
        if self.estado.modo() != "REMOTO":
            return Motivos.SELECTOR_NO_REMOTO
        if tipo is TipoComando.iniciar and self.estado.booleano("estado/nivel_bajo") is True:
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
        }
