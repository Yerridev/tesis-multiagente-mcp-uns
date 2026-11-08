"""Llaves manuales y niveles de los tanques de la PLANTA SIMULADA (una sola verdad para SCADA, lienzos y agentes).

En el laboratorio las llaves V1..V7/VF son de mano: el PLC no las ve. En la planta simulada viven aqui:
  - escucha  <BASE>/sim/cmd/llave   {"id": "V1", "abierta": true}   (lo publica el backend con MODO_PLANTA=simulado)
  - publica  <BASE>/funcional/sim/<ID>        {"value": true|false, ...}   (el backend lo expone como valores["sim/V1"])
             <BASE>/funcional/sim/t1_pct, sim/t2_pct, sim/t1_alto, sim/t1_bajo ...
y cambian la fisica: llenan/vacian tanques, abren o bloquean el camino de la bomba y fijan los
switches de nivel que lee el PLC virtual (T1 con agua / nivel alto).
Si no hay broker MQTT, la planta sigue funcionando con las llaves en su posicion nominal.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone

ALTO, BAJO = 85.0, 15.0          # % de los switches de nivel
LLENADO, VACIADO, TRASVASE = 2.2, 2.5, 2.0   # %/s

RAIZ = "uss/campus/lab-automatizacion/sl01la07"


def _ahora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Llaves:
    """Base comun: estado de las llaves + niveles + puente MQTT."""
    modulo = ""
    nominal: dict[str, bool] = {}
    tanques: dict[str, float] = {"t1": 5.0}      # % inicial (T1 casi vacio -> hay que llenarlo)

    def __init__(self, broker: str | None = None, puerto: int = 1883, nivel_inicial: float | None = None):
        self.base = f"{RAIZ}/{self.modulo}"
        self.abiertas = dict(self.nominal)
        self.nivel = {k: (nivel_inicial if nivel_inicial is not None else v) for k, v in self.tanques.items()}
        self._lock = threading.Lock()
        self._cambio = True
        self._ultimo_pub = 0.0
        self.mq = None
        if broker:
            self._conectar(broker, puerto)

    # ---------------- MQTT ----------------
    def _conectar(self, broker: str, puerto: int):
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("  [llaves] paho-mqtt no instalado: llaves fijas en su posicion nominal")
            return
        try:
            mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-llaves-{self.modulo}")
        except AttributeError:                                  # paho 1.x
            mq = mqtt.Client(client_id=f"sim-llaves-{self.modulo}")

        def on_connect(c, *_a, **_k):
            c.subscribe(f"{self.base}/sim/cmd/#", qos=1)
            self._cambio = True
            print(f"  [llaves] MQTT conectado ({broker}:{puerto}) · escuchando {self.base}/sim/cmd/llave")

        mq.on_connect = on_connect
        mq.on_message = lambda c, u, m: self._mensaje(m.topic, m.payload)
        try:
            mq.connect_async(broker, puerto, keepalive=30)
            mq.loop_start()
            self.mq = mq
        except Exception as ex:                                  # noqa: BLE001
            print(f"  [llaves] sin MQTT ({ex}): llaves fijas en su posicion nominal")

    def _mensaje(self, topic: str, payload: bytes):
        try:
            d = json.loads(payload.decode("utf-8") or "{}")
        except ValueError:
            return
        if topic.endswith("/sim/cmd/llave"):
            ident, abierta = str(d.get("id", "")).upper(), d.get("abierta")
            if ident in self.abiertas and isinstance(abierta, bool):
                with self._lock:
                    self.abiertas[ident] = abierta
                    self._cambio = True
                print(f"  >> llave {ident} {'ABIERTA' if abierta else 'CERRADA'}  (desde el SCADA)")
        elif topic.endswith("/sim/cmd/reiniciar"):
            with self._lock:
                self.abiertas = dict(self.nominal)
                self.nivel = dict(self.tanques)
                self._cambio = True
            print("  >> llaves y tanques reiniciados")

    def publicar(self, forzar: bool = False):
        if not self.mq:
            return
        ahora = time.monotonic()
        if not (forzar or self._cambio or ahora - self._ultimo_pub >= 1.0):
            return
        self._ultimo_pub, self._cambio = ahora, False
        ts = _ahora()
        def pub(clave, valor, unidad=None):
            self.mq.publish(f"{self.base}/funcional/sim/{clave}",
                            json.dumps({"value": valor, "unit": unidad, "source": "simulador", "tag": f"sim/{clave}", "timestamp": ts}),
                            qos=0, retain=True)
        with self._lock:
            for k, v in self.abiertas.items():
                pub(k, v)
            for k, v in self.nivel.items():
                pub(f"{k}_pct", round(v, 1), "%")
                pub(f"{k}_alto", v >= ALTO)
                pub(f"{k}_bajo", v <= BAJO)
        pub("planta", "SIMULADA")

    # ---------------- utilidades ----------------
    def a(self, ident: str) -> bool:
        return self.abiertas.get(ident, False)

    def con_agua(self, t: str = "t1") -> bool:
        return self.nivel[t] > BAJO

    def alto(self, t: str = "t1") -> bool:
        return self.nivel[t] >= ALTO

    def _sumar(self, t: str, delta: float):
        self.nivel[t] = max(0.0, min(100.0, self.nivel[t] + delta))

    def forzar(self, t: str, pct: float):
        """Para los escenarios (p. ej. 'agua_t1': false -> T1 casi vacio)."""
        with self._lock:
            self.nivel[t] = pct
            self._cambio = True

    def resumen(self) -> str:
        ab = ",".join(k for k, v in self.abiertas.items() if v) or "-"
        niv = " ".join(f"{k.upper()}={v:4.1f}%" for k, v in self.nivel.items())
        return f"{niv}  abiertas[{ab}]"

    # cada modulo implementa:
    def antes(self, plc, dt: float): ...
    def despues(self, plc, dt: float): ...


class LlavesNivel(Llaves):
    """MCN-09: bomba T1 -> V4 -> T2; T2 vuelve a T1 por la Belimo. VF llena T1; V7 lo vacia."""
    modulo = "nivel-mcn09"
    nominal = {"V1": False, "V2": False, "V3": False, "V4": True, "V5": False, "VF": False, "V7": False}
    tanques = {"t1": 5.0}
    LITROS_T1 = 78.0

    def antes(self, plc, dt):
        plc.planta.e.agua_t1 = self.con_agua()
        plc.ent.nivel_alto_t1 = self.alto()
        plc.planta.camino_bomba = 1.0 if self.a("V4") else 0.0

    def despues(self, plc, dt):
        pl = plc.planta
        neto_lpm = getattr(pl, "q_out", 0.0) - getattr(pl, "q_in", 0.0)        # lo que vuelve menos lo que sale de T1
        with self._lock:
            self._sumar("t1", neto_lpm / 60.0 / self.LITROS_T1 * 100.0 * dt)
            if self.a("VF"): self._sumar("t1", LLENADO * dt)
            if self.a("V7"): self._sumar("t1", -VACIADO * dt)


class LlavesCaudal(Llaves):
    """MCC-09: bomba T1 -> V5 ... V2 -> T1 (circuito cerrado). VF + V1 llenan T1; V7 lo vacia."""
    modulo = "caudal-mcc09"
    nominal = {"V1": False, "V2": True, "V3": False, "V4": False, "V5": True, "V6": False, "V7": False, "VF": True}
    tanques = {"t1": 5.0}

    def antes(self, plc, dt):
        plc.ent.agua_t1 = self.con_agua()
        plc.ent.nivel_alto = self.alto()
        plc.planta.camino_bomba = 1.0 if (self.a("V5") and self.a("V2")) else 0.0

    def despues(self, plc, dt):
        with self._lock:
            if self.a("VF") and self.a("V1"): self._sumar("t1", LLENADO * dt)
            if self.a("V7"): self._sumar("t1", -VACIADO * dt)


class LlavesPresion(Llaves):
    """MCP-09: bomba T1 -> V5 -> T2 (presurizado); T2 -> proporcional -> V2 -> T1. VF + V1 llenan T1; V7 lo vacia."""
    modulo = "presion-mcp09"
    nominal = {"V1": False, "V2": True, "V3": False, "V4": False, "V5": True, "V6": False, "V7": False, "VF": False}
    tanques = {"t1": 5.0}

    def antes(self, plc, dt):
        plc.planta.e.agua_t1 = self.con_agua()
        plc.ent.nivel_alto_t1 = self.alto()
        plc.planta.camino_bomba = 1.0 if self.a("V5") else 0.0
        plc.planta.camino_retorno = 1.0 if (self.a("V2") or self.a("V3")) else 0.0

    def despues(self, plc, dt):
        with self._lock:
            if self.a("VF") and self.a("V1"): self._sumar("t1", LLENADO * dt)
            if self.a("V7"): self._sumar("t1", -VACIADO * dt)


class LlavesTemperatura(Llaves):
    """MCT-09: VF + V1 llenan T1 (enfriamiento); V2 baja agua de T1 a T2 (principal); V4 vacia T2."""
    modulo = "temperatura-mct09"
    nominal = {"V1": False, "V2": False, "VF": False, "V4": False}
    tanques = {"t1": 5.0, "t2": 5.0}

    def antes(self, plc, dt):
        e = plc.ent
        e.nivel_bajo_enfriador_ok = self.con_agua("t1")
        e.nivel_alto_enfriador = self.alto("t1")
        e.nivel_bajo_principal_ok = self.con_agua("t2")
        e.nivel_alto_principal = self.alto("t2")
        plc.planta.e.agua_enfriador_ok = self.con_agua("t1")

    def despues(self, plc, dt):
        with self._lock:
            if self.a("VF") and self.a("V1"): self._sumar("t1", LLENADO * dt)
            if self.a("V2"):
                q = min(TRASVASE * dt, self.nivel["t1"], 100.0 - self.nivel["t2"])
                self._sumar("t1", -q); self._sumar("t2", q)
            if self.a("V4"): self._sumar("t2", -VACIADO * dt)


class ConLlaves:
    """Envuelve el PLC virtual: aplica las llaves antes y despues de cada scan y publica su estado."""
    def __init__(self, plc, llaves: Llaves):
        self.plc, self.llaves = plc, llaves

    def scan(self, dt: float):
        self.llaves.antes(self.plc, dt)
        self.plc.scan(dt)
        self.llaves.despues(self.plc, dt)
        self.llaves.publicar()

    def resumen(self) -> str:
        return f"{self.plc.resumen()}  |  {self.llaves.resumen()}"

    def __getattr__(self, nombre):
        return getattr(self.plc, nombre)
