"""Modelos de la API (contrato con el frontend React).

Reglas que reproduce el backend ASP.NET original:

* **camelCase** en el JSON (``alias_generator=to_camel``).
* **Enums como texto** con el nombre PascalCase exacto (``Confirmado``,
  ``Iniciar``...).  FastAPI serializa un ``str, Enum`` por su valor, así que
  basta con declarar el valor igual al nombre.
* **Fechas con offset**: se usan ``datetime`` con zona horaria; Pydantic las
  serializa en ISO-8601, que es lo que ``new Date(...)`` del navegador
  entiende.
* Los campos que el C# enviaba y el frontend no usa (p. ej. ``overrideCalidad``)
  se conservan para no perder información de auditoría.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ModeloApi(BaseModel):
    """Base de todos los modelos: serializa en camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# ============================================================ enums del contrato de control
class TipoComando(str, Enum):
    iniciar = "Iniciar"
    detener = "Detener"
    reiniciar = "Reiniciar"
    setpoint = "Setpoint"
    parametro_pid = "ParametroPid"
    abrir_valvula = "AbrirValvula"
    cerrar_valvula = "CerrarValvula"
    ajustar_valvula = "AjustarValvula"
    potencia_variador = "PotenciaVariador"


class EstadoComando(str, Enum):
    recibido = "Recibido"
    validando = "Validando"
    enviado = "Enviado"
    aceptado = "Aceptado"
    escrito = "Escrito"
    confirmado = "Confirmado"
    rechazado = "Rechazado"
    vencido = "Vencido"
    timeout = "Timeout"
    error = "Error"


class ModoAgente(str, Enum):
    llm = "llm"
    reglas = "rules"
    multiagente = "multiagente"


class RolTurno(str, Enum):
    user = "user"
    agente = "agente"


# ============================================================ salud
class HealthInfo(ModeloApi):
    status: str
    service: str
    timestamp: datetime


# ============================================================ autenticación
class SolicitudLogin(ModeloApi):
    usuario: str | None = None
    password: str | None = None


class RespuestaLogin(ModeloApi):
    token: str
    usuario: str
    nombre: str
    rol: str
    expira: datetime


class EstadoAuth(ModeloApi):
    habilitado: bool
    listo: bool | None = None
    horas_sesion: int | None = None


class YoModelo(ModeloApi):
    habilitado: bool
    usuario: str
    nombre: str
    rol: str
    expira: datetime | None = None


class SolicitudUsuario(ModeloApi):
    usuario: str | None = None
    nombre: str | None = None
    rol: str | None = None
    password: str | None = None
    activo: bool | None = None


class UsuarioFila(ModeloApi):
    id: int
    usuario: str
    nombre: str
    rol: str
    activo: bool
    creado: datetime
    ultimo_acceso: datetime | None = None


class AccesoFila(ModeloApi):
    id: int
    ts: datetime
    usuario: str
    evento: str
    ip: str | None = None
    detalle: str | None = None


# ============================================================ planta y señales
class EquipmentState(ModeloApi):
    id: str
    name: str
    controller: str
    ip: str
    variable: str
    value: float | None = None
    unit: str
    setpoint: float
    timestamp: datetime
    status: str
    deviation: float
    alarm: bool
    calidad: str = "buena"


class HistorySample(ModeloApi):
    id: str
    variable: str
    unit: str
    value: float
    ts: datetime


class LevelDetail(ModeloApi):
    equipment_id: str
    name: str
    controller: str
    plc_ip: str
    plc_status: str
    mode: str | None = None
    level: float | None = None
    unit: str
    setpoint: float | None = None
    tank_height: float | None = None
    percent: float | None = None
    pump_on: bool | None = None
    vfd_hz: float | None = None
    vfd_percent: float | None = None
    valve_open: float | None = None
    high_alarm: bool | None = None
    low_alarm: bool | None = None
    valvula_abriendo: bool | None = None
    valvula_cerrando: bool | None = None
    timestamp: datetime | None = None
    calidad: str = "buena"


class SenalValor(ModeloApi):
    valor: Any = None
    unidad: str | None = None
    source: str | None = None
    tag: str | None = None
    ts: datetime | None = None


class SenalesModulo(ModeloApi):
    """Snapshot de señales de un módulo (el C# lo llamaba ``NivelSenales``)."""

    mqtt: bool
    edge: str | None = None
    plc: str | None = None
    mensajes: int = 0
    ultimo: datetime | None = None
    heartbeat: datetime | None = None
    altura_cm: float | None = None
    tema_base: str
    valores: dict[str, SenalValor] = Field(default_factory=dict)


# ============================================================ control
class SolicitudComando(ModeloApi):
    """Solicitud entrante. Solo comandos SEMÁNTICOS: el navegador jamás
    envía una dirección del PLC (eso lo resuelve el conector contra su
    allowlist)."""

    tipo: str | None = None
    valor: float | None = None
    parametro: str | None = None
    unidad: str | None = None
    equipo: str | None = None
    comentario: str | None = None
    correlacion: str | None = None
    origen: str | None = None


class OrdenControl(ModeloApi):
    id: str
    tipo: TipoComando
    valor: float | None = None
    parametro: str | None = None
    unidad: str | None = None
    equipo: str
    comentario: str | None = None
    correlacion: str | None = None
    origen: str | None = None
    usuario: str
    rol: str
    modo: str
    estado: EstadoComando
    motivo: str | None = None
    expedida: datetime
    expira: datetime
    timeout_en: datetime
    actualizada: datetime | None = None
    escrito: bool | None = None
    valor_esperado: float | None = None
    valor_leido: float | None = None
    override_calidad: bool = False


class ConfiguracionControl(ModeloApi):
    modo: str
    habilitado_escritura: bool
    control_real: str | None = None
    timeout_segundos: int
    expiracion_segundos: int


class ProcesoNivel(ModeloApi):
    simulador: bool
    plc: str
    selector: str | None = None
    nivel_bajo_t1: bool | None = None
    mqtt_nivel: bool
    fuente_control: str | None = None
    sensor_saturado: bool
    override_calidad: bool


class ProcesoModulo(ModeloApi):
    plc: str
    selector: str | None = None
    mqtt: bool | None = None
    nivel_bajo_t1: bool | None = None
    mandando_el_pc: bool | None = None
    variador_v: float | None = None
    valvula_v: float | None = None
    falla_principal: bool | None = None
    falla_enfriador: bool | None = None


class TelemetriaControl(ModeloApi):
    ultimo: datetime | None = None
    edad_segundos: float | None = None
    fresca: bool
    max_segundos: int


class EstadoControlNivel(ModeloApi):
    modo_efectivo: str
    real_armado: bool
    motivos_real: list[str]
    configuracion: ConfiguracionControl
    proceso: ProcesoNivel
    telemetria: TelemetriaControl
    pendientes: int


class EstadoControlModulo(ModeloApi):
    modo_efectivo: str
    real_armado: bool
    proceso: ProcesoModulo
    telemetria: TelemetriaControl
    pendientes: int


class DireccionPermitida(ModeloApi):
    tag: str
    direccion: str
    tipo: str
    verificada: bool
    uso: str | None = None


class ContratoControl(ModeloApi):
    equipo: str
    topicos: dict[str, str]
    tipos: list[dict[str, Any]]
    estados: list[str]
    confirmacion: dict[str, str]
    motivos: list[str]
    salidas_prohibidas: list[str]
    allowlist: list[DireccionPermitida]
    estado: dict[str, Any]


# ============================================================ agentes
class AgentTool(ModeloApi):
    name: str
    server: str
    description: str


class AgentCall(ModeloApi):
    name: str
    ok: bool
    ms: int
    result: str


class AgentReply(ModeloApi):
    reply: str
    agent: str
    ts: datetime
    tools: list[AgentCall]
    mode: ModoAgente = ModoAgente.reglas
    model: str | None = None
    conversacion_id: str | None = None


class ModeloOpenRouter(ModeloApi):
    id: str
    nombre: str
    gratis: bool


class AgentStatus(ModeloApi):
    mode: str
    enabled: bool
    model: str
    models: list[ModeloOpenRouter] = Field(default_factory=list)
    provider: str
    scope: str
    multiagente: bool | None = None


class TurnoChat(ModeloApi):
    rol: str | None = None
    texto: str | None = None


class AgentAskRequest(ModeloApi):
    message: str | None = None
    model: str | None = None
    history: list[TurnoChat] | None = None
    conversacion_id: str | None = None
    origen: str | None = None


class MensajeGuardado(ModeloApi):
    rol: str
    texto: str
    ts: datetime
    modelo: str | None = None
    modo: str | None = None
    herramientas: list[AgentCall] | None = None
    ms: int | None = None


class ConversacionResumen(ModeloApi):
    id: str
    origen: str
    usuario: str | None = None
    titulo: str
    creada: datetime
    actualizada: datetime
    mensajes: int
    modelos: list[str]


class ConversacionCompleta(ModeloApi):
    id: str
    origen: str
    usuario: str | None = None
    titulo: str
    creada: datetime
    actualizada: datetime
    mensajes: list[MensajeGuardado]


# ============================================================ lienzos y simulación
class LienzoLayout(ModeloApi):
    posiciones: dict[str, dict[str, float]] = Field(default_factory=dict)
    lados: dict[str, dict[str, str]] = Field(default_factory=dict)
    ts: datetime | None = None


class SolicitudLlave(ModeloApi):
    modulo: str | None = None
    id: str | None = None
    abierta: bool = False


class RespuestaSimulacion(ModeloApi):
    ok: bool
    modulo: str | None = None
    id: str | None = None
    abierta: bool | None = None


class EstadoPlanta(ModeloApi):
    modo: str
