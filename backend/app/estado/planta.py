"""Estado de la planta: equipos, calidad del dato e historial en memoria.

Equivale a ``PlantState.cs``.  Puntos clave que se conservan:

* todos los equipos arrancan **sin telemetría** (marca de tiempo epoch → OFFLINE);
* el sensor de nivel saturado **anula** el valor y **no** alimenta el historial
  (el valor en cm sería el tope de la escala, no una medida);
* sin calidad conocida del dato de nivel, el valor en cm no se acepta
  (fail-closed);
* la alarma solo se evalúa con telemetría fresca.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from ..modulos import MODULOS, NIVEL
from .modulo import EstadoModulo

log = logging.getLogger(__name__)

#: Banda de alarma: ±12 % de la consigna.
TOLERANCIA = 0.12

#: Antigüedad máxima (s) para considerar un equipo ONLINE.
FRESCURA_S = 15

#: Capacidad del búfer de historial por equipo (~30 min de muestras a 1 Hz).
CAPACIDAD_HISTORIAL = 1800

#: Marcas de tiempo de la calidad del dato.
CALIDAD_BUENA = "buena"
CALIDAD_FUERA_DE_RANGO = "sensor_fuera_de_rango"
CALIDAD_SIN_CALIDAD = "sin_calidad"


def _ahora() -> datetime:
    return datetime.now().astimezone()


class PlantState:
    """Estado consolidado de los cuatro equipos."""

    def __init__(self, estados: dict[str, EstadoModulo]) -> None:
        self.estados = estados
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}
        self._historial: dict[str, deque] = {}
        self._ultimo_push: dict[str, datetime | None] = {}

        for modulo in MODULOS:
            self._items[modulo.clave] = {
                "id": modulo.clave,
                "name": modulo.nombre,
                "controller": modulo.controlador,
                "ip": modulo.ip,
                "variable": modulo.variable,
                "value": 0.0,
                "unit": modulo.unidad,
                "setpoint": modulo.consigna,
                "timestamp": datetime.fromtimestamp(0, tz=timezone.utc),
                "calidad": CALIDAD_BUENA,
            }
            self._historial[modulo.clave] = deque(maxlen=CAPACIDAD_HISTORIAL)
            self._ultimo_push[modulo.clave] = None

    # ------------------------------------------------------------------ lecturas
    def todos(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._presentar(self._items[m.clave]) for m in MODULOS]

    def obtener(self, clave: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(clave)
            return self._presentar(item) if item else None

    def historial(self, clave: str | None, limite: int) -> list[dict[str, Any]]:
        limite = max(1, min(5000, limite if limite and limite > 0 else 300))
        with self._lock:
            if clave:
                cola = self._historial.get(clave)
                return [dict(s) for s in cola] if cola else []
            muestras = [m for cola in self._historial.values() for m in cola]
            muestras.sort(key=lambda s: s["ts"])
            return [dict(m) for m in muestras[-limite:]]

    # ------------------------------------------------------------------ actualización
    def aplicar(self) -> None:
        """Refresca los equipos con la última telemetría conocida."""
        for modulo in MODULOS:
            estado = self.estados.get(modulo.clave)
            if estado is None:
                continue
            if modulo.clave == NIVEL.clave:
                self._aplicar_nivel(estado)
            elif modulo.clave == "caudal-mcc09":
                self._aplicar_caudal(estado)
            elif modulo.clave == "presion-mcp09":
                self._aplicar_presion(estado)
            else:
                self._aplicar_temperatura(estado)

    def _aplicar_nivel(self, estado: EstadoModulo) -> None:
        # La frescura se mide con el HEARTBEAT del conector edge (el que lee el
        # PLC), no con el último mensaje MQTT: el conector de control sigue
        # publicando aunque el edge o el PLC ya no respondan.
        ts = estado.ultimo_heartbeat or estado.ultimo_mensaje
        if ts is None:
            return                       # nunca ha llegado un mensaje real
        cm = estado.numero("nivel/cm")
        with self._lock:
            actual = self._items[NIVEL.clave]
            if estado.sensor_saturado:
                # El valor en cm NO es una medida: se anula y NO alimenta el historial.
                self._items[NIVEL.clave] = {**actual, "value": None, "timestamp": ts,
                                            "calidad": CALIDAD_FUERA_DE_RANGO}
                return
            if not estado.calidad_conocida:
                self._items[NIVEL.clave] = {**actual, "value": None, "timestamp": ts,
                                            "calidad": CALIDAD_SIN_CALIDAD}
                return
            valor = round(cm, 2) if cm is not None else actual["value"]
            consigna = estado.setpoint_cm()
            self._items[NIVEL.clave] = {
                **actual,
                "value": valor,
                "setpoint": consigna if consigna is not None else actual["setpoint"],
                "timestamp": ts,
                "calidad": CALIDAD_BUENA,
            }
            if cm is not None and self._ultimo_push[NIVEL.clave] != ts:
                self._ultimo_push[NIVEL.clave] = ts
                self._push(NIVEL.clave, actual["variable"], actual["unit"], valor, ts)

    def _aplicar_simple(self, clave: str, estado: EstadoModulo, valor: float | None,
                        consigna: float | None, decimales: int, usar_ultima_telemetria: bool) -> None:
        ts = estado.ultima_telemetria if usar_ultima_telemetria else estado.ultimo_mensaje
        if ts is None:
            return
        # Sello de tiempo = hora del DATO mientras el lector (edge) siga latiendo; si su
        # heartbeat se queda viejo, se congela en el último latido -> a los 15 s OFFLINE.
        # (Usar siempre el heartbeat congelaba la tendencia: el frontend solo agrega
        # muestras cuando el sello avanza y el latido llega cada 10 s con hora del conector.)
        hb = estado.ultimo_heartbeat
        hb_fresco = hb is None or (_ahora() - hb).total_seconds() <= FRESCURA_S
        vivo = ts if hb_fresco else hb
        caido = (estado.plc_conexion or "").strip().upper() == "SIN_CONEXION"
        with self._lock:
            actual = self._items[clave]
            nuevo_valor = valor if valor is not None else actual["value"]
            self._items[clave] = {
                **actual,
                "value": round(nuevo_valor, decimales),
                "setpoint": round(consigna if consigna is not None else actual["setpoint"], 2),
                "timestamp": actual["timestamp"] if caido else vivo,
            }
            if valor is not None and not caido and self._ultimo_push[clave] != ts:
                self._ultimo_push[clave] = ts
                self._push(clave, actual["variable"], actual["unit"],
                           round(valor, decimales), ts)

    def _aplicar_caudal(self, estado: EstadoModulo) -> None:
        pv = estado.numero("caudal/pv_pid")
        medidor = estado.numero("caudal/caudalimetro")
        self._aplicar_simple("caudal-mcc09", estado, pv if pv is not None else medidor,
                             estado.numero("caudal/setpoint"), 2, False)

    def _aplicar_presion(self, estado: EstadoModulo) -> None:
        self._aplicar_simple("presion-mcp09", estado, estado.numero("presion/psi"),
                             estado.numero("pid/setpoint_pc"), 3, False)

    def _aplicar_temperatura(self, estado: EstadoModulo) -> None:
        self._aplicar_simple("temp-mct09", estado, estado.numero("temperatura/principal_c"),
                             estado.numero("pid/setpoint_c"), 2, True)

    def _push(self, clave: str, variable: str, unidad: str, valor: float, ts: datetime) -> None:
        cola = self._historial.get(clave)
        if cola is None:
            return
        cola.append({"id": clave, "variable": variable, "unit": unidad,
                     "value": valor, "ts": ts})

    # ------------------------------------------------------------------ presentación
    def _presentar(self, item: dict[str, Any]) -> dict[str, Any]:
        """Calcula status / deviation / alarm (los campos derivados del C#)."""
        valor = item["value"]
        consigna = item["setpoint"]
        ts = item["timestamp"]
        calidad = item["calidad"]
        fresco = (_ahora() - ts).total_seconds() <= FRESCURA_S
        medible = calidad == CALIDAD_BUENA and valor is not None
        desviacion = round(valor - consigna, 2) if valor is not None else 0.0
        alarma = bool(
            medible
            and consigna != 0
            and fresco
            and abs(valor - consigna) > max(1e-6, abs(consigna) * TOLERANCIA)
        )
        return {
            **item,
            "status": "ONLINE" if fresco else "OFFLINE",
            "deviation": desviacion,
            "alarm": alarma,
        }

    # ------------------------------------------------------------------ detalle nivel
    def detalle_nivel(self) -> dict[str, Any]:
        """Detalle del módulo de nivel construido SOLO con datos reales."""
        estado = self.estados.get(NIVEL.clave)
        if estado is None:                                # pragma: no cover
            estado = EstadoModulo(NIVEL)
        with self._lock:
            equipo = dict(self._items[NIVEL.clave])

        saturado = estado.sensor_saturado
        medible = not saturado and estado.calidad_conocida

        plc_online = (
            estado.mqtt_conectado
            and estado.plc_conectado
            and estado.ultimo_heartbeat is not None
            and (_ahora() - estado.ultimo_heartbeat).total_seconds() <= 25
        )
        calidad = (
            CALIDAD_FUERA_DE_RANGO if saturado
            else (CALIDAD_BUENA if estado.calidad_conocida else CALIDAD_SIN_CALIDAD)
        )
        return {
            "equipmentId": NIVEL.clave,
            "name": "Tanque MCN-09",
            "controller": equipo["controller"],
            "plcIp": equipo["ip"],
            "plcStatus": "ONLINE" if plc_online else "OFFLINE",
            "mode": estado.modo(),
            "level": estado.numero("nivel/cm") if medible else None,
            "unit": "cm",
            "setpoint": estado.setpoint_cm(),
            "tankHeight": estado.altura_tanque_cm,
            "percent": estado.numero("nivel/pct") if medible else None,
            "pumpOn": estado.booleano("estado/bomba_marcha"),
            "vfdHz": estado.numero("bomba/frecuencia_estimada_hz"),
            "vfdPercent": estado.vfd_porcentaje(),
            "valveOpen": None,              # no hay % real de apertura
            "highAlarm": None,
            "lowAlarm": None,
            "valvulaAbriendo": estado.booleano("valvula/abriendo"),
            "valvulaCerrando": estado.booleano("valvula/cerrando"),
            "timestamp": estado.ultimo_mensaje,
            "calidad": calidad,
        }

    # ------------------------------------------------------------------ resumen
    def resumen_historial(self) -> str:
        partes = []
        with self._lock:
            for clave, cola in self._historial.items():
                if not cola:
                    continue
                valores = [m["value"] for m in cola]
                partes.append(
                    f"{clave}: {len(valores)} muestras, "
                    f"mín {min(valores):.2f}, prom {sum(valores)/len(valores):.2f}, "
                    f"máx {max(valores):.2f}"
                )
        return " · ".join(partes) if partes else "sin muestras"


def snapshot_planta(planta: PlantState) -> list[dict[str, Any]]:
    """Refresca y devuelve el estado de los equipos (lo que se empuja por SSE)."""
    planta.aplicar()
    return planta.todos()
