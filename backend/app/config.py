"""Configuración del backend.

Equivalente directo del ``IConfiguration`` de ASP.NET Core: se lee
``backend/appsettings.json`` y se sobreescribe con variables de entorno usando
``__`` como separador de secciones (``Mqtt__Host`` -> sección ``Mqtt``, clave
``Host``).  La variable de entorno SIEMPRE gana, igual que en .NET.

El formato y los nombres son los mismos que usa el compose actual, de modo que
``compose.yaml`` no necesita cambios para migrar de C# a Python.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]          # raíz del repositorio
BACKEND = Path(__file__).resolve().parents[1]       # .../backend


def _a_bool(valor: Any, defecto: bool) -> bool:
    if valor is None:
        return defecto
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in {"1", "true", "yes", "si", "sí", "on"}:
        return True
    if texto in {"0", "false", "no", "off"}:
        return False
    return defecto


def _a_int(valor: Any, defecto: int) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return defecto


def _a_float(valor: Any, defecto: float) -> float:
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return defecto


def _nodo(datos: dict[str, Any], nombre: str) -> dict[str, Any]:
    """Devuelve la subsección ``nombre`` (buscando sin distinguir mayúsculas).

    En Windows ``os.environ`` normaliza las claves a MAYÚSCULAS, así que
    ``Mqtt__Port`` llega como ``MQTT__PORT``.  .NET resolvía la configuración
    sin distinguir mayúsculas; aquí se hace lo mismo.
    """
    for clave, valor in datos.items():
        if clave.lower() == nombre.lower() and isinstance(valor, dict):
            return valor
    nuevo: dict[str, Any] = {}
    datos[nombre] = nuevo
    return nuevo


def _inyectar_entorno(datos: dict[str, Any]) -> None:
    """Vuelca las variables ``SECCION__Clave`` dentro del diccionario de config."""
    for nombre, valor in os.environ.items():
        if "__" not in nombre:
            continue
        seccion, _, clave = nombre.partition("__")
        if not clave:
            continue
        nodo = _nodo(datos, seccion)
        # si la clave ya existe (appsettings), se sobrescribe conservando su forma
        for existente in nodo:
            if existente.lower() == clave.lower():
                nodo[existente] = valor
                break
        else:
            nodo[clave] = valor


def _leer_json(ruta: Path) -> dict[str, Any]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def _seccion(datos: dict[str, Any], nombre: str) -> dict[str, Any]:
    """Subsección ``nombre`` (búsqueda sin distinguir mayúsculas; no crea nada)."""
    valor = _clave(datos, nombre)
    return dict(valor) if isinstance(valor, dict) else {}


def _clave(seccion: dict[str, Any], nombre: str) -> Any:
    """Valor de una clave (sin distinguir mayúsculas)."""
    if nombre in seccion:
        return seccion[nombre]
    for clave, valor in seccion.items():
        if clave.lower() == nombre.lower():
            return valor
    return None


def _texto(seccion: dict[str, Any], clave: str, defecto: str | None = None) -> str | None:
    valor = _clave(seccion, clave)
    if valor is None:
        return defecto
    texto = str(valor).strip()
    return texto if texto else defecto


def _entorno_real(nombre: str) -> str | None:
    valor = os.environ.get(nombre)
    return valor.strip() if valor else None


# --------------------------------------------------------------------------- MQTT
@dataclass(frozen=True)
class MqttCfg:
    host: str = "127.0.0.1"
    port: int = 1883
    nivel_topico: str | None = None
    caudal_control_host: str | None = None
    caudal_control_port: int = 1883
    presion_control_host: str | None = None
    presion_control_port: int = 1883
    temperatura_control_host: str | None = None
    temperatura_control_port: int = 1883
    agentes_host: str | None = None
    agentes_port: int = 1883

    @property
    def host_agentes(self) -> str:
        return self.agentes_host or self.caudal_control_host or self.host

    @property
    def port_agentes(self) -> int:
        return self.agentes_port or self.port


# --------------------------------------------------------------------------- control
@dataclass
class ControlCfg:
    """Opciones de control del módulo de nivel (MCN-09)."""

    modo: str = "DryRun"
    habilitado_escritura: bool = False
    timeout_segundos: int = 10
    expiracion_segundos: int = 15
    ventana_duplicados_segundos: int = 30
    topico_base: str = "uss/campus/lab-automatizacion/sl01la07/nivel-mcn09/control"
    auditoria_ruta: str | None = None
    usuarios: dict[str, str] = field(default_factory=dict)
    permitir_sensor_fuera_de_rango: bool = False
    variable_entorno_real: str | None = None

    #: Si es False, el backend NO publica órdenes en MQTT (instancias de solo
    #: lectura, p. ej. el stack paralelo).  La orden se rechaza con el motivo
    #: PUBLICACION_DESHABILITADA.  Con True (por defecto) se comporta como el
    #: backend de producción.
    publicar: bool = True

    def topico(self, sufijo: str) -> str:
        return f"{self.topico_base}/{sufijo}"


@dataclass
class ControlModuloCfg:
    """Opciones de control de caudal / presión / temperatura (contratos propios)."""

    modo: str = "DryRun"
    habilitado_escritura: bool = False
    timeout_segundos: int = 12
    expiracion_segundos: int = 20
    topico_base: str = ""
    variable_entorno_real: str | None = None

    def topico(self, sufijo: str) -> str:
        return f"{self.topico_base}/{sufijo}"


# --------------------------------------------------------------------------- seguridad
@dataclass
class AuthCfg:
    habilitado: bool = True
    conexion: str | None = None
    horas_sesion: int = 8
    admin_usuario: str | None = None
    admin_password: str | None = None
    token_servicio: str | None = None


@dataclass
class OpenRouterCfg:
    api_key: str = ""
    model: str = "openrouter/free"
    max_tokens: int = 1600
    timeout_segundos: int = 90
    modelos: list[str] = field(default_factory=list)


@dataclass
class HealthCfg:
    database_enabled: bool = False
    database_host: str = "timescaledb"
    database_port: int = 5432


# --------------------------------------------------------------------------- raíz
@dataclass
class Config:
    mqtt: MqttCfg = field(default_factory=MqttCfg)
    control: ControlCfg = field(default_factory=ControlCfg)
    control_caudal: ControlModuloCfg = field(default_factory=ControlModuloCfg)
    control_presion: ControlModuloCfg = field(default_factory=ControlModuloCfg)
    control_temperatura: ControlModuloCfg = field(default_factory=ControlModuloCfg)
    auth: AuthCfg = field(default_factory=AuthCfg)
    openrouter: OpenRouterCfg = field(default_factory=OpenRouterCfg)
    health: HealthCfg = field(default_factory=HealthCfg)
    agente_conversaciones_ruta: str | None = None
    agente_multiagente_timeout: int = 150
    lienzo_ruta: str | None = None
    planta_modo: str = "real"
    agents_only: bool = False
    datos: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers
    @property
    def ruta_wwwroot(self) -> Path:
        """Carpeta con la SPA compilada (la sirve el backend)."""
        return BACKEND / "wwwroot"

    def valor(self, seccion: str, clave: str, defecto: Any = None) -> Any:
        return _clave(_seccion(self.datos, seccion), clave) if _clave(_seccion(self.datos, seccion), clave) is not None else defecto


_USUARIOS_DEV_POR_DEFECTO = {
    "dev-viewer": "viewer",
    "dev-operador": "operador",
    "dev-supervisor": "supervisor",
    "dev-admin": "admin",
}


def cargar_config() -> Config:
    """Construye la configuración desde appsettings.json + variables de entorno."""
    datos = _leer_json(BACKEND / "appsettings.json")
    _inyectar_entorno(datos)

    mqtt_s = _seccion(datos, "Mqtt")
    mqtt = MqttCfg(
        host=_texto(mqtt_s, "Host", "127.0.0.1") or "127.0.0.1",
        port=_a_int(_clave(mqtt_s, "Port"), 1883),
        nivel_topico=_texto(mqtt_s, "NivelTopico"),
        caudal_control_host=_texto(mqtt_s, "CaudalControlHost"),
        caudal_control_port=_a_int(_clave(mqtt_s, "CaudalControlPort"), 1883),
        presion_control_host=_texto(mqtt_s, "PresionControlHost"),
        presion_control_port=_a_int(_clave(mqtt_s, "PresionControlPort"), 1883),
        temperatura_control_host=_texto(mqtt_s, "TemperaturaControlHost"),
        temperatura_control_port=_a_int(_clave(mqtt_s, "TemperaturaControlPort"), 1883),
        agentes_host=_texto(mqtt_s, "AgentesHost"),
        agentes_port=_a_int(_clave(mqtt_s, "AgentesPort"), 1883),
    )

    control_s = _seccion(datos, "Control")
    usuarios = {k: str(v) for k, v in _seccion(control_s, "Usuarios").items()}
    if not usuarios:
        usuarios = dict(_USUARIOS_DEV_POR_DEFECTO)
    control = ControlCfg(
        modo=_texto(control_s, "Modo", "DryRun") or "DryRun",
        habilitado_escritura=_a_bool(_clave(control_s, "HabilitadoEscritura"), False),
        timeout_segundos=_a_int(_clave(control_s, "TimeoutSegundos"), 10),
        expiracion_segundos=_a_int(_clave(control_s, "ExpiracionSegundos"), 15),
        ventana_duplicados_segundos=_a_int(_clave(control_s, "VentanaDuplicadosSegundos"), 30),
        topico_base=_texto(control_s, "TopicoBase", ControlCfg.topico_base) or ControlCfg.topico_base,
        auditoria_ruta=_texto(control_s, "AuditoriaRuta"),
        usuarios=usuarios,
        permitir_sensor_fuera_de_rango=_a_bool(
            _clave(control_s, "PermitirSensorFueraDeRango"),
            _a_bool(os.environ.get("CONTROL_PERMITIR_SENSOR_FUERA_DE_RANGO"), False),
        ),
        variable_entorno_real=_entorno_real("CONTROL_REAL"),
        publicar=_a_bool(_clave(control_s, "Publicar"), True),
    )

    def _modulo(seccion: str, prefijo: str, topico_defecto: str) -> ControlModuloCfg:
        s = _seccion(datos, seccion)
        return ControlModuloCfg(
            modo=_texto(s, "Modo", "DryRun") or "DryRun",
            habilitado_escritura=_a_bool(_clave(s, "HabilitadoEscritura"), False),
            timeout_segundos=_a_int(_clave(s, "TimeoutSegundos"), 12),
            expiracion_segundos=_a_int(_clave(s, "ExpiracionSegundos"), 20),
            topico_base=_texto(s, "TopicoBase", topico_defecto) or topico_defecto,
            variable_entorno_real=_entorno_real(prefijo),
        )

    control_caudal = _modulo(
        "ControlCaudal", "CONTROL_CAUDAL_REAL",
        "uss/campus/lab-automatizacion/sl01la07/caudal-mcc09/control",
    )
    control_presion = _modulo(
        "ControlPresion", "CONTROL_PRESION_REAL",
        "uss/campus/lab-automatizacion/sl01la07/presion-mcp09/control",
    )
    control_temperatura = _modulo(
        "ControlTemperatura", "CONTROL_TEMPERATURA_REAL",
        "uss/campus/lab-automatizacion/sl01la07/temperatura-mct09/control",
    )

    auth_s = _seccion(datos, "Auth")
    auth = AuthCfg(
        habilitado=_a_bool(_clave(auth_s, "Habilitado"), True),
        conexion=_texto(auth_s, "Conexion"),
        horas_sesion=_a_int(_clave(auth_s, "HorasSesion"), 8),
        admin_usuario=_texto(auth_s, "AdminUsuario"),
        admin_password=_texto(auth_s, "AdminPassword"),
        token_servicio=_texto(auth_s, "TokenServicio"),
    )
    if not auth.conexion:
        auth.habilitado = False

    llm_s = _seccion(datos, "OpenRouter")
    modelos = _texto(llm_s, "Models", "") or ""
    openrouter = OpenRouterCfg(
        api_key=_texto(llm_s, "ApiKey", "") or "",
        model=_texto(llm_s, "Model", "openrouter/free") or "openrouter/free",
        max_tokens=_a_int(_clave(llm_s, "MaxTokens"), 1600),
        timeout_segundos=_a_int(_clave(llm_s, "TimeoutSeconds"), 90),
        modelos=[m.strip() for m in modelos.split(",") if m.strip()],
    )

    health_s = _seccion(datos, "Health")
    health = HealthCfg(
        database_enabled=_a_bool(_clave(health_s, "DatabaseEnabled"), False),
        database_host=_texto(health_s, "DatabaseHost", "timescaledb") or "timescaledb",
        database_port=_a_int(_clave(health_s, "DatabasePort"), 5432),
    )

    agente_s = _seccion(datos, "Agente")
    planta_modo = (_texto(_seccion(datos, "Planta"), "Modo", "") or os.environ.get("MODO_PLANTA", "real")).strip().lower()
    if planta_modo != "simulado":
        planta_modo = "real"

    return Config(
        mqtt=mqtt,
        control=control,
        control_caudal=control_caudal,
        control_presion=control_presion,
        control_temperatura=control_temperatura,
        auth=auth,
        openrouter=openrouter,
        health=health,
        agente_conversaciones_ruta=_texto(agente_s, "ConversacionesRuta"),
        agente_multiagente_timeout=_a_int(_clave(agente_s, "MultiagenteTimeoutSegundos"), 150),
        lienzo_ruta=_texto(_seccion(datos, "Lienzo"), "Ruta"),
        planta_modo=planta_modo,
        agents_only=_a_bool(os.environ.get("AGENTS_ONLY"), False),
        datos=datos,
    )


_CONFIG: Config | None = None


def config() -> Config:
    """Configuración única del proceso (se construye al importar la app)."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = cargar_config()
    return _CONFIG


def reiniciar_config() -> None:
    """Solo para pruebas: fuerza a releer appsettings + entorno."""
    global _CONFIG
    _CONFIG = None
