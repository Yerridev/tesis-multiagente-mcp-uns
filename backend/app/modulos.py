"""Registro de los cuatro módulos de la planta.

Fuente única de verdad para: base MQTT (UNS), metadatos del equipo que ve el
frontend y particularidades de cada módulo (cómo se llama el estado del
selector, qué contrato de control aplica).

Equivale a los ``const Base`` de ``NivelState/CaudalState/PresionState/
TemperaturaState`` y a la tabla de equipos de ``PlantState``.
"""

from __future__ import annotations

from dataclasses import dataclass

UNS = "uss/campus/lab-automatizacion/sl01la07"


@dataclass(frozen=True)
class Modulo:
    clave: str                  # id del equipo (el que usa el frontend)
    nombre: str                 # nombre visible
    controlador: str            # tipo de PLC
    ip: str
    variable: str               # "Nivel", "Caudal", ...
    unidad: str
    consigna: float             # consigna inicial hasta que llegue del PLC
    base_mqtt: str              # raíz de tópicos del módulo
    evento_senales: str         # evento SSE con su snapshot de señales
    modo_remoto: str            # etiqueta cuando manda el control remoto
    modo_local: str             # etiqueta cuando manda el tablero
    modo_desconocido: str       # etiqueta cuando no se sabe
    modo_nulo_si_desconocido: bool = False   # nivel: null en vez de etiqueta
    equipo_control: str = ""    # id de equipo del contrato de control
    unidad_control: str = ""
    telemetria_max_segundos: int = 15

    @property
    def topico_funcional(self) -> str:
        return f"{self.base_mqtt}/funcional"


NIVEL = Modulo(
    clave="nivel-mcn09",
    nombre="Control de nivel",
    controlador="MicroLogix 1100",
    ip="192.168.114.9",
    variable="Nivel",
    unidad="cm",
    consigna=0.0,
    base_mqtt=f"{UNS}/nivel-mcn09",
    evento_senales="nivelSenales",
    modo_remoto="REMOTO",
    modo_local="LOCAL",
    modo_desconocido="EN 0",
    modo_nulo_si_desconocido=True,
    equipo_control="nivel-mcn09",
    unidad_control="cm",
    telemetria_max_segundos=30,
)

CAUDAL = Modulo(
    clave="caudal-mcc09",
    nombre="Control de caudal",
    controlador="Siemens S7-200",
    ip="192.168.114.7",
    variable="Caudal",
    unidad="L/min",
    consigna=75.0,
    base_mqtt=f"{UNS}/caudal-mcc09",
    evento_senales="caudalSenales",
    modo_remoto="REMOTO",
    modo_local="LOCAL",
    modo_desconocido="DESCONOCIDO",
    equipo_control="caudal-mcc09",
    unidad_control="L/min",
)

PRESION = Modulo(
    clave="presion-mcp09",
    nombre="Control de presión",
    controlador="NI cFP-2200",
    ip="192.168.114.8",
    variable="Presión",
    unidad="psi",
    consigna=22.0,
    base_mqtt=f"{UNS}/presion-mcp09",
    evento_senales="presionSenales",
    modo_remoto="REMOTO",
    modo_local="LOCAL",
    modo_desconocido="DESCONOCIDO",
    equipo_control="presion-mcp09",
    unidad_control="psi",
)

TEMPERATURA = Modulo(
    clave="temp-mct09",
    nombre="Control de temperatura",
    controlador="Schneider Twido",
    ip="192.168.114.10",
    variable="Temperatura",
    unidad="°C",
    consigna=40.0,
    base_mqtt=f"{UNS}/temperatura-mct09",
    evento_senales="temperaturaSenales",
    modo_remoto="PC",
    modo_local="HMI",
    modo_desconocido="SIN_SELECCION",
    equipo_control="temp-mct09",
    unidad_control="C",
)

MODULOS: tuple[Modulo, ...] = (CAUDAL, NIVEL, PRESION, TEMPERATURA)

POR_CLAVE: dict[str, Modulo] = {m.clave: m for m in MODULOS}
