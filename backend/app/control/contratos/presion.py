"""Control del MCP-09 (cFP-2200).

El PID corre en el controlador: el SCADA solo escribe consigna, ganancias y la
toma/cesión de mando (variables de red del cFP-2200).
"""

from __future__ import annotations

from typing import Any

from ...modelos import TipoComando
from ..contrato import Motivos
from .base import ControlModulo

#: Variables de red del cFP-2200 que el SCADA puede escribir.  La consigna PC
#: forma parte del diseño original del supervisor y se confirma por lectura
#: posterior.
VARIABLES_AUTORIZADAS = (
    "DATOS_PAC/INICIO_PC", "DATOS_PAC/SALIR_PC", "pid/setpoint_pc",
    "pid/Kp_PC", "pid/Ti_PC", "pid/Td_PC",
)

LAZO_EN_EL_CONTROLADOR = (
    "LAZO_EN_EL_CONTROLADOR: la consigna y el PID se gobiernen en el cFP-2200 "
    "(panel HMI o app RT)"
)

AJUSTE_SOLO_CON_SISTEMA_DETENIDO = "AJUSTE_SOLO_CON_SISTEMA_DETENIDO"
AJUSTE_PENDIENTE_DE_CONFIRMACION = "AJUSTE_PENDIENTE_DE_CONFIRMACION"


class PresionControl(ControlModulo):
    clave = "presion"
    equipo = "presion-mcp09"
    unidad = "psi"
    telemetria_max_segundos = 15
    evento_resultado = "presionControlResultado"
    host_config = "presion_control_host"
    port_config = "presion_control_port"
    tipos_admitidos = frozenset({
        TipoComando.iniciar, TipoComando.detener, TipoComando.setpoint,
        TipoComando.parametro_pid,
    })

    def validar(self, solicitud, tipo: TipoComando) -> str | None:
        valor = solicitud.valor

        def fuera(minimo: float, maximo: float) -> bool:
            return (valor is None or valor != valor or valor in (float("inf"), float("-inf"))
                    or valor < minimo or valor > maximo)

        if tipo is TipoComando.setpoint:
            if (solicitud.unidad or "").strip().lower() != self.unidad.lower():
                return Motivos.UNIDAD_INVALIDA
            if fuera(0, 40):
                return Motivos.RANGO_INVALIDO
        elif tipo is TipoComando.parametro_pid:
            parametro = (solicitud.parametro or "").lower()
            if parametro not in ("kp", "kc", "ti", "td"):
                return Motivos.TIPO_DESCONOCIDO
            maximo = 20 if parametro in ("kp", "kc") else (60 if parametro == "ti" else 10)
            if fuera(0, maximo):
                return Motivos.RANGO_INVALIDO
        elif tipo is TipoComando.ajustar_valvula:
            return LAZO_EN_EL_CONTROLADOR
        elif tipo in (TipoComando.reiniciar, TipoComando.abrir_valvula, TipoComando.cerrar_valvula):
            return Motivos.TIPO_DESCONOCIDO
        return None

    def preflight(self, solicitud, tipo: TipoComando) -> str | None:
        if not self.real_armado():
            return Motivos.REAL_NO_ARMADO
        if not self.estado.plc_conectado:
            return Motivos.PLC_DESCONECTADO
        # El mando automático (DI Ch0 = SEL_AUTO) es condición física: en LOCAL el
        # control lo hacen los pulsadores del tablero y el SCADA no debe escribir.
        if self.estado.booleano("estado/selector_remoto") is not True:
            return Motivos.SELECTOR_NO_REMOTO
        es_ajuste = tipo in (TipoComando.setpoint, TipoComando.parametro_pid)
        if es_ajuste and self.estado.booleano("estado/control_pc") is not True:
            return Motivos.CONTROL_EN_HMI
        if es_ajuste and (self.estado.booleano("estado/sistema_funcionando") is True
                          or self.estado.booleano("estado/bomba_habilitada") is True):
            return AJUSTE_SOLO_CON_SISTEMA_DETENIDO
        edad = self._edad_telemetria()
        if edad is None or edad > self.telemetria_max_segundos:
            return Motivos.TELEMETRIA_VENCIDA

        # No se solapan ajustes: mientras un Setpoint/PID está sin confirmar no
        # se admite otro, ni siquiera un arranque.
        pendientes = [o for o in self._ordenes.values()
                      if not o.es_terminal and o.tipo in (TipoComando.setpoint, TipoComando.parametro_pid)]
        if es_ajuste and pendientes:
            return Motivos.DUPLICADA
        if tipo is TipoComando.iniciar and pendientes:
            return AJUSTE_PENDIENTE_DE_CONFIRMACION
        return None

    def proceso_publico(self) -> dict[str, Any]:
        return {
            "plc": "CONECTADO" if self.estado.plc_conectado else "DESCONECTADO",
            "selector": self.estado.modo(),
            "mqtt": self.estado.mqtt_conectado,
            "mandandoElPc": self.estado.booleano("estado/pulsador_arranque"),
            "variadorV": self.estado.numero("bomba/salida_variador"),
            "valvulaV": self.estado.numero("valvula/salida"),
        }
