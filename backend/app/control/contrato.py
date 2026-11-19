"""Contrato de control remoto: tipos, estados, motivos, rangos y allowlist.

Port de ``Control/ControlContrato.cs``.  Reglas de seguridad que se conservan:

* el navegador **nunca** envía una dirección del PLC: solo comandos semánticos;
* el guard duro rechaza cualquier escritura sobre salidas de proceso
  (``O:0/*`` y ``O:1/*``) aunque la allowlist cambie;
* toda dirección candidata sale marcada ``verificada=False`` → ``NO_VERIFICADAS``
  salvo las confirmadas en la campaña de laboratorio;
* los roles ordenan la operación: viewer < operador < supervisor < admin.
"""

from __future__ import annotations

from dataclasses import dataclass

# Los enums viven en app.modelos (una sola fuente de verdad para toda la API:
# el frontend compara los NOMBRES exactos).  Se re-exportan aquí para que el
# contrato se pueda usar como antes.
from ..modelos import EstadoComando, TipoComando

__all__ = [
    "TipoComando", "EstadoComando", "ESTADOS_FINALES", "Motivos", "TODOS_MOTIVOS",
    "DireccionPermitida", "ALLOWLIST_NIVEL", "ControlContrato",
]


#: Estados que cierran la orden.  Aceptado/Escrito NO son terminales: esperan
#: la confirmación leída.
ESTADOS_FINALES = frozenset({
    EstadoComando.confirmado, EstadoComando.rechazado,
    EstadoComando.vencido, EstadoComando.timeout, EstadoComando.error,
})


# --------------------------------------------------------------------------- motivos
class Motivos:
    """Códigos de error normalizados (motivo de rechazo)."""

    RANGO_INVALIDO = "RANGO_INVALIDO"
    TIPO_DESCONOCIDO = "TIPO_DESCONOCIDO"
    PERMISO_INSUFICIENTE = "PERMISO_INSUFICIENTE"
    SIN_AUTENTICACION = "SIN_AUTENTICACION"
    PLC_DESCONECTADO = "PLC_DESCONECTADO"
    SELECTOR_NO_REMOTO = "SELECTOR_NO_REMOTO"
    CONTROL_EN_HMI = "CONTROL_EN_HMI"
    FUENTE_CONTROL_SIN_DATO = "FUENTE_CONTROL_SIN_DATO"
    NIVEL_BAJO_T1 = "NIVEL_BAJO_T1"
    DUPLICADA = "DUPLICADA"
    VENCIDA = "VENCIDA"
    SIN_CONFIRMACION = "SIN_CONFIRMACION"
    MQTT_NO_DISPONIBLE = "MQTT_NO_DISPONIBLE"
    DIRECCION_PROHIBIDA = "DIRECCION_PROHIBIDA"
    REAL_NO_ARMADO = "REAL_NO_ARMADO"
    EQUIPO_INVALIDO = "EQUIPO_INVALIDO"
    UNIDAD_INVALIDA = "UNIDAD_INVALIDA"
    TELEMETRIA_VENCIDA = "TELEMETRIA_VENCIDA"
    NIVEL_SENSOR_FUERA_DE_RANGO = "NIVEL_SENSOR_FUERA_DE_RANGO"
    NIVEL_CALIDAD_DESCONOCIDA = "NIVEL_CALIDAD_DESCONOCIDA"
    CONFIRMACION_NO_COINCIDE = "CONFIRMACION_NO_COINCIDE"
    DIRECCION_NO_PERMITIDA = "DIRECCION_NO_PERMITIDA"
    DIRECCION_NO_VERIFICADA = "DIRECCION_NO_VERIFICADA"
    #: Esta instancia es de SOLO LECTURA: no publica órdenes en MQTT (Control__Publicar=false).
    PUBLICACION_DESHABILITADA = "PUBLICACION_DESHABILITADA"


TODOS_MOTIVOS = [
    Motivos.RANGO_INVALIDO, Motivos.TIPO_DESCONOCIDO, Motivos.PERMISO_INSUFICIENTE,
    Motivos.SIN_AUTENTICACION, Motivos.PLC_DESCONECTADO, Motivos.SELECTOR_NO_REMOTO,
    Motivos.NIVEL_BAJO_T1, Motivos.DUPLICADA, Motivos.CONTROL_EN_HMI,
    Motivos.FUENTE_CONTROL_SIN_DATO, Motivos.VENCIDA, Motivos.SIN_CONFIRMACION,
    Motivos.MQTT_NO_DISPONIBLE, Motivos.DIRECCION_PROHIBIDA, Motivos.REAL_NO_ARMADO,
    Motivos.EQUIPO_INVALIDO, Motivos.UNIDAD_INVALIDA, Motivos.TELEMETRIA_VENCIDA,
    Motivos.CONFIRMACION_NO_COINCIDE, Motivos.NIVEL_SENSOR_FUERA_DE_RANGO,
    Motivos.NIVEL_CALIDAD_DESCONOCIDA, Motivos.DIRECCION_NO_PERMITIDA,
    Motivos.DIRECCION_NO_VERIFICADA,
]


# --------------------------------------------------------------------------- allowlist
@dataclass(frozen=True)
class DireccionPermitida:
    tag: str
    direccion: str
    tipo: str
    verificada: bool
    uso: str | None = None


#: Allowlist de direcciones candidatas del MCN-09 (extraídas del RSS y del
#: conector edge).  Evidencia de rung:
#: MCN\07_PLC_RSLOGIX\ladder_control_nivel_micrologix1100.md (programa vigente).
ALLOWLIST_NIVEL: tuple[DireccionPermitida, ...] = (
    DireccionPermitida("B3:0/3", "B3:0/3", "bit", True,
                       "PC_HMI: 0=PC 1=HMI (verificada en ladder online; rung 0005/0007/0022)"),
    DireccionPermitida("B3:0/4", "B3:0/4", "bit", True,
                       "START_PC: 1=marcha sostenida, 0=parada (verificada en ladder online; rung 0005)"),
    DireccionPermitida("B3:0/5", "B3:0/5", "bit", False,
                       "START_HMI (externo): NIVEL; rung 0007/0009"),
    DireccionPermitida("B3:0/13", "B3:0/13", "bit", True,
                       "START_VALVU: pulso para movimiento temporizado por N7:1/N7:2"),
    DireccionPermitida("N7:5", "N7:5", "entero", True,
                       "Setpoint PC -> PD12:0.SPS (rung 0022); raw=16348-400*cm"),
    DireccionPermitida("N7:6", "N7:6", "entero", False,
                       "Setpoint HMI -> PD12:0.SPS (rung 0022) en cuentas"),
    DireccionPermitida("N7:8", "N7:8", "entero", True, "KC PC -> PD12:0.KC; valor web x100 con RG=1"),
    DireccionPermitida("N7:9", "N7:9", "entero", True, "Ti PC -> PD12:0.Ti; valor web x100 con RG=1"),
    DireccionPermitida("N7:10", "N7:10", "entero", True, "TD PC -> PD12:0.TD; valor web x100 con RG=1"),
    DireccionPermitida("N7:11", "N7:11", "entero", False, "KC HMI -> PD12:0.KC (rung 0022)"),
    DireccionPermitida("N7:12", "N7:12", "entero", False, "Ti HMI -> PD12:0.Ti (rung 0022)"),
    DireccionPermitida("N7:13", "N7:13", "entero", False, "TD HMI -> PD12:0.TD (rung 0022)"),
    DireccionPermitida("N7:1", "N7:1", "entero", True,
                       "Tiempo apertura -> T4:0.PRE; calibrado 9500=95 s"),
    DireccionPermitida("N7:2", "N7:2", "entero", True,
                       "Tiempo cierre -> T4:1.PRE; calibrado 9500=95 s"),
)


# --------------------------------------------------------------------------- contrato
class ControlContrato:
    """Contrato de comandos del nivel MCN-09: rangos, permisos, estados y errores."""

    # Rangos de proceso (tanque T2 de 0-40 cm según equipos.json; PID en unidades del PD12:0)
    SETPOINT_MIN = 0.0
    SETPOINT_MAX = 40.0          # cm
    KP_MIN = 0.0
    KP_MAX = 50.0
    TI_MIN = 0.0
    TI_MAX = 600.0               # s (o s/min según configuración del PD12)
    TD_MIN = 0.0
    TD_MAX = 60.0
    APERTURA_MIN = 0.0
    APERTURA_MAX = 100.0         # %

    #: Referencia del variador (cuentas escritas en N7:0).
    POTENCIA_VARIADOR_MIN = 0.0
    POTENCIA_VARIADOR_MAX = 32000.0

    #: Equipo exacto admitido por el contrato (no se aceptan direcciones ni ids arbitrarios).
    EQUIPO = "nivel-mcn09"

    #: Unidad obligatoria del setpoint.
    UNIDAD_SETPOINT = "cm"

    #: Segundos máximos de antigüedad de la telemetría del edge para expedir órdenes.
    TELEMETRIA_MAX_SEGUNDOS = 30

    #: Tipos que el conector de control del MCN-09 implementa de verdad.
    #: ``AjustarValvula`` es exclusivo del MCC-09 (caudal): aquí se rechaza con
    #: TIPO_DESCONOCIDO en vez de publicar una orden que el conector descarta.
    TIPOS_ADMITIDOS = frozenset({
        TipoComando.iniciar, TipoComando.detener, TipoComando.reiniciar,
        TipoComando.setpoint, TipoComando.parametro_pid,
        TipoComando.abrir_valvula, TipoComando.cerrar_valvula,
        TipoComando.potencia_variador,
    })

    #: Guard duro: jamás se escribe sobre salidas de proceso.
    @staticmethod
    def es_salida_prohibida(direccion: str) -> bool:
        return direccion.upper().startswith("O:0") or direccion.upper().startswith("O:1")

    @staticmethod
    def rol_minimo(tipo: TipoComando) -> str:
        """Rol mínimo por tipo de comando."""
        if tipo in (TipoComando.iniciar, TipoComando.detener, TipoComando.reiniciar):
            return "operador"
        return "supervisor"      # setpoint, PID, válvula y variador requieren supervisor

    @staticmethod
    def rol_suficiente(rol: str | None, tipo: TipoComando) -> bool:
        if not rol or not rol.strip():
            return False
        minimo = ControlContrato.rol_minimo(tipo)
        match rol.strip().lower():
            case "admin" | "supervisor":
                return True
            case "operador":
                return minimo == "operador"
            case _:
                return False      # viewer o desconocido

    @staticmethod
    def parsear_tipo(texto: str | None) -> TipoComando | None:
        if not texto or not texto.strip():
            return None
        try:
            tipo = TipoComando(texto.strip())
        except ValueError:
            return None
        return tipo if tipo in ControlContrato.TIPOS_ADMITIDOS else None

    @staticmethod
    def validar_valor(tipo: TipoComando, valor: float | None) -> str | None:
        """Valida el rango del valor. Devuelve el motivo de error si no cumple."""
        if tipo is TipoComando.setpoint:
            return ControlContrato._rango(valor, ControlContrato.SETPOINT_MIN,
                                          ControlContrato.SETPOINT_MAX)
        if tipo is TipoComando.potencia_variador:
            return ControlContrato._rango(valor, ControlContrato.POTENCIA_VARIADOR_MIN,
                                          ControlContrato.POTENCIA_VARIADOR_MAX)
        return None

    @staticmethod
    def validar_pid(parametro: str | None, valor: float | None) -> str | None:
        """Valida el rango de un parámetro PID con nombre (kp/ti/td)."""
        if not parametro or not parametro.strip():
            return Motivos.TIPO_DESCONOCIDO
        match parametro.strip().lower():
            case "kp":
                return ControlContrato._rango(valor, ControlContrato.KP_MIN, ControlContrato.KP_MAX)
            case "ti":
                return ControlContrato._rango(valor, ControlContrato.TI_MIN, ControlContrato.TI_MAX)
            case "td":
                return ControlContrato._rango(valor, ControlContrato.TD_MIN, ControlContrato.TD_MAX)
            case _:
                return Motivos.TIPO_DESCONOCIDO

    @staticmethod
    def _rango(valor: float | None, minimo: float, maximo: float) -> str | None:
        if valor is None or valor != valor or valor in (float("inf"), float("-inf")):
            return Motivos.RANGO_INVALIDO
        return Motivos.RANGO_INVALIDO if valor < minimo or valor > maximo else None
