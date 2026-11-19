"""Estado de un módulo: lo que llega por MQTT desde el conector edge.

Une los cuatro ``*State`` de C# (``NivelState``, ``CaudalState``,
``PresionState``, ``TemperaturaState``) en una sola clase parametrizada por
``Modulo``.  Los únicos que tenían comportamiento propio son el de nivel
(consigna en cm, saturación del sensor, propietario del mando) y el de
temperatura (modo "PC"/"HMI" y la última telemetría); ambos quedan aquí
resueltos con ``if modulo.clave == ...``.

REGLA: aquí no se simula NADA.  Si no llega un mensaje, el campo queda a null
y la interfaz muestra SIN DATOS.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from ..modulos import Modulo, NIVEL

log = logging.getLogger(__name__)

#: Umbral de saturación del sensor ultrasónico (cuentas de N7:4).  Por debajo,
#: el sensor está saturado o muerto y el valor en cm es el TOPE de la escala,
#: no una medida.  Mismo criterio que el conector edge (LIMITE_SENSOR_RAW).
LIMITE_SENSOR_RAW = 300

#: Conversión de la escala del nivel: cm = (16348 - cuentas) / 400.
RAW_NIVEL_BASE = 16348
RAW_NIVEL_FACTOR = 400.0


def _ahora() -> datetime:
    return datetime.now().astimezone()


def _parsear_ts(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


class EstadoModulo:
    """Estado real de un módulo, alimentado únicamente por MQTT."""

    def __init__(self, modulo: Modulo) -> None:
        self.modulo = modulo
        self._lock = threading.Lock()
        self._valores: dict[str, dict[str, Any]] = {}
        self.mqtt_conectado = False
        self.edge_estado: str | None = None
        self.plc_conexion: str | None = None
        self.ultimo_mensaje: datetime | None = None
        self.ultimo_heartbeat: datetime | None = None
        self.ultima_telemetria: datetime | None = None
        self.altura_tanque_cm: float | None = None
        self.mensajes = 0

    # ------------------------------------------------------------------ entrada
    @property
    def clave(self) -> str:
        """Id del equipo (nivel-mcn09, caudal-mcc09, ...)."""
        return self.modulo.clave

    def aplicar(self, topico: str, payload: str) -> None:
        """Aplica un mensaje MQTT (tópico completo + payload en texto)."""
        base = self.modulo.base_mqtt
        if not topico.lower().startswith(base.lower()):
            return
        relativo = topico[len(base):].lstrip("/")

        self.mensajes += 1
        self.ultimo_mensaje = _ahora()

        if relativo.lower().startswith("descriptivo/"):
            # Metadatos del conector (catálogo y calibración): no es dato de proceso.
            if relativo.lower().endswith("equipo"):
                self._leer_altura_tanque(payload)
            return

        if not relativo.lower().startswith("funcional/"):
            return
        sufijo = relativo[len("funcional/"):]

        clave = sufijo.lower()
        if clave == "edge/estado":
            self.edge_estado = payload.strip()
            return
        if clave == "plc/conexion":
            self.plc_conexion = payload.strip()
            return
        if clave == "edge/heartbeat":
            self.ultimo_heartbeat = _parsear_ts(payload.strip())
            return
        if clave in {"descriptivo/equipo", "descriptivo/variables"}:
            return

        dato = self._parsear(payload)
        self._valores[sufijo] = dato

        from .latencia import registrar

        registrar(self.modulo.clave.split("-")[0], sufijo, dato.get("ts"))

        if self.modulo.clave == "temp-mct09":
            # Al (re)conectar llegan mensajes RETENIDOS viejos en cualquier orden:
            # la última telemetría es la MÁS RECIENTE, nunca un retenido antiguo.
            momento = dato.get("ts") or _ahora()
            if self.ultima_telemetria is None or momento > self.ultima_telemetria:
                self.ultima_telemetria = momento

    @staticmethod
    def _parsear(payload: str) -> dict[str, Any]:
        """Convierte el payload del conector edge (``{"value": ..., "unit": ...}``)."""
        texto = payload.strip()
        if texto.startswith("{"):
            try:
                raiz = json.loads(texto)
            except ValueError:
                raiz = None
            if isinstance(raiz, dict):
                valor = raiz.get("value")
                if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                    valor = float(valor)
                elif not isinstance(valor, (bool, str, type(None))):
                    valor = None
                return {
                    "valor": valor,
                    "unidad": raiz.get("unit"),
                    "source": raiz.get("source"),
                    "tag": raiz.get("tag"),
                    "ts": _parsear_ts(raiz.get("timestamp")),
                }
        return {"valor": texto, "unidad": None, "source": None, "tag": None, "ts": None}

    def _leer_altura_tanque(self, payload: str) -> None:
        try:
            raiz = json.loads(payload)
            calibracion = raiz.get("calibracion_nivel") or {}
            altura = calibracion.get("altura_tanque2_cm")
            if isinstance(altura, (int, float)):
                self.altura_tanque_cm = float(altura)
        except (ValueError, AttributeError):
            pass    # metadatos ilegibles: no afecta a los datos de proceso

    # ------------------------------------------------------------------ lecturas
    def get(self, sufijo: str) -> dict[str, Any] | None:
        return self._valores.get(sufijo.lower()) or self._valores.get(sufijo)

    def numero(self, sufijo: str) -> float | None:
        dato = self.get(sufijo)
        if dato is None:
            return None
        valor = dato.get("valor")
        if valor is None:
            return None
        if isinstance(valor, bool):
            return 1.0 if valor else 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        if isinstance(valor, str):
            try:
                return float(valor.strip())
            except ValueError:
                return None
        return None

    def booleano(self, sufijo: str) -> bool | None:
        """Lee el valor crudo y lo interpreta como booleano.

        Acepta lo que publican los conectores edge: JSON ``{"value": true}``,
        texto plano ``"true"`` y números (1/0).  Equivale al ``Bool()`` del
        backend original.
        """
        dato = self.get(sufijo)
        if dato is None:
            return None
        valor = dato.get("valor")
        if valor is None:
            return None
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, (int, float)):
            return abs(float(valor)) > 0.5
        if isinstance(valor, str):
            texto = valor.strip().lower()
            if texto in {"true", "1", "on", "yes"}:
                return True
            if texto in {"false", "0", "off", "no"}:
                return False
            try:
                return abs(float(texto)) > 0.5
            except ValueError:
                return None
        return None

    def texto(self, sufijo: str) -> str | None:
        dato = self.get(sufijo)
        if dato is None:
            return None
        valor = dato.get("valor")
        if valor is None:
            return None
        if isinstance(valor, bool):
            return "ON" if valor else "OFF"
        return str(valor)

    @property
    def plc_conectado(self) -> bool:
        return (self.plc_conexion or "").strip().upper() == "CONECTADO"

    def modo(self) -> str | None:
        """Estado del selector: REMOTO/LOCAL/... según el módulo."""
        remoto = self.booleano("estado/selector_remoto")
        local = self.booleano("estado/selector_local")
        if remoto is None and local is None:
            return None if self.modulo.modo_nulo_si_desconocido else self.modulo.modo_desconocido
        if remoto is True:
            return self.modulo.modo_remoto
        if local is True:
            return self.modulo.modo_local
        return self.modulo.modo_desconocido

    # ------------------------------------------------------- particularidades
    @property
    def es_nivel(self) -> bool:
        return self.modulo.clave == NIVEL.clave

    def fuente_control(self) -> str | None:
        """Propietario del mando remoto según B3:0/3: PC o HMI."""
        valor = (self.texto("estado/fuente_control") or "").strip().upper()
        return valor if valor in {"PC", "HMI"} else None

    def setpoint_cm(self) -> float | None:
        """Consigna activa en cm (N7:5 del PC o N7:6 del HMI)."""
        if not self.es_nivel:
            return None
        crudo = self.numero("pid/setpoint_b_raw" if self.fuente_control() == "HMI"
                            else "pid/setpoint_a_raw")
        if crudo is None:
            return None
        cm = (RAW_NIVEL_BASE - crudo) / RAW_NIVEL_FACTOR
        return round(cm, 2) if 0 <= cm <= 60 else None

    def vfd_porcentaje(self) -> float | None:
        """Frecuencia del variador en % sobre su escala 0–50 Hz."""
        hz = self.numero("bomba/frecuencia_estimada_hz")
        if hz is None:
            return None
        return round(max(0.0, min(100.0, hz / 50 * 100)), 1)

    @property
    def sensor_saturado(self) -> bool:
        """El sensor está saturado o fuera de rango: el valor en cm NO es una medida."""
        if not self.es_nivel:
            return False
        if self.booleano("nivel/fuera_rango_sensor") is True:
            return True
        crudo = self.numero("nivel/raw")
        return crudo is not None and crudo < LIMITE_SENSOR_RAW

    @property
    def calidad_conocida(self) -> bool:
        """¿Se conoce la calidad del dato de nivel? (fail-closed: sin dato, no se mueve)"""
        if not self.es_nivel:
            return True
        return self.numero("nivel/raw") is not None or self.get("nivel/fuera_rango_sensor") is not None

    # ------------------------------------------------------------------ salida
    def snapshot(self) -> dict[str, Any]:
        """Copia serializable para el REST y el canal SSE."""
        base = {
            "mqtt": self.mqtt_conectado,
            "edge": self.edge_estado,
            "plc": self.plc_conexion,
            "mensajes": self.mensajes,
            "ultimo": self.ultimo_mensaje,
            "heartbeat": self.ultimo_heartbeat,
            "temaBase": self.modulo.base_mqtt,
            "valores": {k: dict(v) for k, v in self._valores.items()},
        }
        if self.modulo.clave == "temp-mct09":
            base["ultimaTelemetria"] = self.ultima_telemetria
        if self.es_nivel:
            base["alturaCm"] = self.altura_tanque_cm
        return base

    # ------------------------------------------------------------------ MQTT
    async def consumir(self, ctx) -> None:
        """Mantiene la suscripción MQTT viva (reconecta sola)."""
        from ..mqtt.suscriptor import consumir_topico

        topico = ctx.cfg.mqtt.nivel_topico or f"{self.modulo.base_mqtt}/#"
        await consumir_topico(
            ctx,
            topico,
            self.aplicar,
            cliente_id=f"mcp-industrial-{self.modulo.clave}",
            al_conectar=self._conectar,
            al_desconectar=self._desconectar,
        )

    def _conectar(self) -> None:
        self.mqtt_conectado = True

    def _desconectar(self) -> None:
        self.mqtt_conectado = False
