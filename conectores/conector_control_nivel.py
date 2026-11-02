#!/usr/bin/env python3
"""
Conector de CONTROL (órdenes) para el módulo de nivel MCN-09 — solo para desarrollo y
campaña de laboratorio. NUNCA escribe salidas de proceso (O:0/*, O:1/*) y NUNCA escribe
si la dirección no está VERIFICADA en la allowlist.

Tópicos (misma base que el UNS del conector edge):
  cmd   :uss/.../nivel-mcn09/control/cmd    (recibido, JSON del backend)
  ack   :uss/.../nivel-mcn09/control/ack    (publicado, JSON: ACEPTADO → ESCRITO → CONFIRMADO | RECHAZADO)
  state :uss/.../nivel-mcn09/control/state  (publicado, JSON periódico)

Además se SUSCRIBE a uss/.../nivel-mcn09/funcional/# para revalidar por su cuenta:
  - conexión con el PLC (funcional/plc/conexion)
  - selector físico REMOTO/LOCAL (funcional/estado/selector_remoto)
  - frescura de la telemetría del edge (último mensaje visto)

Modos (--modo):
  dry-run   (por defecto)  Valida la orden (doble validación) y publica ACEPTADO +
                           CONFIRMADO con escrito=false. NO toca el PLC. Si el edge
                           demuestra PLC caído/selector LOCAL/telemetría vieja, RECHAZA.
  simulador                Imita al PLC en memoria para probar el flujo completo
                           (ACEPTADO → CONFIRMADO, escrito=false, modo=SIMULADOR).
  real                     Requiere TODO a la vez: --habilitado-real + env CONTROL_REAL=1
                           + selector físico REMOTO (I:0/0) + dirección VERIFICADA en la
                           allowlist. Hoy 0/13 direcciones están VERIFICADAS ⇒ real
                           siempre rechaza. La única función que podría escribir es
                           escribir_direccion_verificada(), encapsulada y con doble gate.

Uso (venv del historiador):
  ..\\historiador\\.venv\\Scripts\\python.exe conector_control_nivel.py --modo dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt

BASE = "uss/campus/lab-automatizacion/sl01la07/nivel-mcn09"
CTRL = f"{BASE}/control"
FUNC = f"{BASE}/funcional"

EQUIPO = "nivel-mcn09"
UNIDAD_SETPOINT = "cm"
TELEMETRIA_MAX_S = 60.0          # edge: sin mensajes por más de esto → RECHAZADO en real

# Rangos del contrato (deben coincidir con ControlContrato.cs)
RANGOS = {
    "Setpoint": (0.0, 40.0),      # cm sobre el tanque T2
    "kp": (0.0, 50.0),
    "ti": (0.0, 600.0),
    "td": (0.0, 60.0),
}

# Direcciones candidatas (extraídas del RSS/edge). TODAS NO_VERIFICADAS:
# se confirman en laboratorio con RSLogix antes de cualquier escritura real.
# "escritura" = nivel (mantener el bit) | pulso (ON y volver a cero).
# Evidencia de rung: MCN\07_PLC_RSLOGIX\ladder_control_nivel_micrologix1100.md
ALLOWLIST = [
    {"tag": "B3:0/3", "direccion": "B3:0/3", "tipo": "bit", "verificada": True, "escritura": "nivel", "uso": "PC_HMI: 0=PC 1=HMI (verificada en ladder online; rung 0005/0007/0022)"},
    {"tag": "B3:0/4", "direccion": "B3:0/4", "tipo": "bit", "verificada": True, "escritura": "nivel", "uso": "START_PC: 1=marcha sostenida, 0=parada (verificada en ladder online; rung 0005)"},
    {"tag": "B3:0/5", "direccion": "B3:0/5", "tipo": "bit", "verificada": False, "escritura": "nivel", "uso": "START_HMI (externo): NIVEL; rung 0007/0009"},
    {"tag": "B3:0/13", "direccion": "B3:0/13", "tipo": "bit", "verificada": True, "escritura": "pulso", "uso": "START_VALVU: dispara movimiento temporizado por N7:1/N7:2"},
    {"tag": "N7:5", "direccion": "N7:5", "tipo": "entero", "verificada": True, "escritura": "registro", "uso": "Setpoint PC -> PD12:0.SPS (rung 0022); raw=16348-400*cm"},
    {"tag": "N7:6", "direccion": "N7:6", "tipo": "entero", "verificada": False, "escritura": "registro", "uso": "Setpoint HMI -> PD12:0.SPS (rung 0022) en cuentas"},
    {"tag": "N7:8", "direccion": "N7:8", "tipo": "entero", "verificada": True, "escritura": "registro", "uso": "KC PC -> PD12:0.KC; valor web x100 (RG=1)"},
    {"tag": "N7:9", "direccion": "N7:9", "tipo": "entero", "verificada": True, "escritura": "registro", "uso": "Ti PC -> PD12:0.Ti; valor web x100 (RG=1)"},
    {"tag": "N7:10", "direccion": "N7:10", "tipo": "entero", "verificada": True, "escritura": "registro", "uso": "TD PC -> PD12:0.TD; valor web x100 (RG=1)"},
    {"tag": "N7:11", "direccion": "N7:11", "tipo": "entero", "verificada": False, "escritura": "registro", "uso": "KC HMI -> PD12:0.KC (rung 0022)"},
    {"tag": "N7:12", "direccion": "N7:12", "tipo": "entero", "verificada": False, "escritura": "registro", "uso": "Ti HMI -> PD12:0.Ti (rung 0022)"},
    {"tag": "N7:13", "direccion": "N7:13", "tipo": "entero", "verificada": False, "escritura": "registro", "uso": "TD HMI -> PD12:0.TD (rung 0022)"},
    {"tag": "N7:1", "direccion": "N7:1", "tipo": "entero", "verificada": True, "escritura": "registro", "uso": "Tiempo apertura -> T4:0.PRE; calibrado 9500=95 s"},
    {"tag": "N7:2", "direccion": "N7:2", "tipo": "entero", "verificada": True, "escritura": "registro", "uso": "Tiempo cierre -> T4:1.PRE; calibrado 9500=95 s"},
]

# Dirección candidata por tipo de comando (null = sin candidata confirmada todavía).
# Detener: soltar START_PC apaga el lazo (sello en serie rung 0005 + watchdog T4:4 1.02 s).
DIRECCION_POR_TIPO = {
    "Iniciar": "B3:0/4",
    "Detener": "B3:0/4",
    "Reiniciar": None,        # el ladder no tiene reinicio por PC
    "Setpoint": "N7:5",
    "AbrirValvula": "B3:0/13",
    "CerrarValvula": "B3:0/13",
}

# Valor numérico a escribir por comando (bits: Iniciar=1 sostenido, Detener=0)
VALOR_POR_COMANDO = {"Iniciar": 1, "Detener": 0}
PID_POR_PARAMETRO = {"kp": "N7:8", "ti": "N7:9", "td": "N7:10"}

TIPOS = ("Iniciar", "Detener", "Reiniciar", "Setpoint", "ParametroPid", "AbrirValvula", "CerrarValvula")


def es_direccion_prohibida(direccion: str) -> bool:
    """Rechaza salidas O:0/O:1, entradas I:* y salidas de estado S:* — jamás se escriben."""
    d = direccion.upper()
    return (d.startswith("O:0") or d.startswith("O:1") or
            d.startswith("I:") or d.startswith("S:"))


def buscar_allowlist(direccion: str):
    for e in ALLOWLIST:
        if e["direccion"].upper() == direccion.upper():
            return e
    return None


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Conector:
    def __init__(self, modo: str, plc_ip: str, habilitado_real: bool, pulso_ms: int = 500):
        self.modo = modo                      # dry-run | simulador | real
        self.plc_ip = plc_ip
        self.habilitado_real = habilitado_real
        self.pulso_ms = pulso_ms
        self.vistos: "OrderedDict[str, float]" = OrderedDict()
        self.procesadas = 0
        self.ultimo_ack = None
        self.plc = None                       # solo en modo real (pycomm3.SLCDriver)
        # ---- estado del edge (suscripción a funcional/#) para doble validación
        self.edge_ultimo = None               # datetime del último mensaje del edge
        self.plc_edge = None                  # CONECTADO | DESCONECTADO | None
        self.selector_remoto = None           # True | False | None
        self.fuente_control = None             # PC | HMI | None (B3:0/3; solo lectura)
        self.posicion_valvula = 100.0          # calibrada físicamente en esta puesta en marcha

    # ------------------------------------------------------------- etiquetas
    def log(self, etiqueta: str, msg: str) -> None:
        print(f"[{self.etiqueta()}] {etiqueta}: {msg}", flush=True)

    def etiqueta(self) -> str:
        return {"dry-run": "DRY-RUN", "simulador": "SIMULADOR", "real": "REAL"}[self.modo]

    # ------------------------------------------------------------- estado
    def estado(self) -> dict:
        return {
            "modo": self.etiqueta(),
            "simulador": self.modo == "simulador",
            "plc": "SIMULADOR" if self.modo == "simulador" else ("CONECTADO" if self.modo == "real" and self.plc else "SIN_CONEXION"),
            "habilitado_real": self.habilitado_real,
            "env_control_real": os.environ.get("CONTROL_REAL"),
            "procesadas": self.procesadas,
            "verificadas": sum(1 for e in ALLOWLIST if e["verificada"]),
            "edge": {
                "ultimo": self.edge_ultimo.isoformat() if self.edge_ultimo else None,
                "plc": self.plc_edge,
                "selector_remoto": self.selector_remoto,
                "fuente_control": self.fuente_control,
            },
            "visto": ahora_iso(),
            "host": socket.gethostname(),
        }

    # ------------------------------------------------- telemetría del edge
    def registrar_edge(self, topico: str, payload: str) -> None:
        """Actualiza el estado del edge a partir de funcional/# (solo lectura)."""
        self.edge_ultimo = datetime.now(timezone.utc)
        rel = topico[len(FUNC):].strip("/") if topico.startswith(FUNC) else topico
        valor = payload.strip()
        try:
            decodificado = json.loads(valor)
            if isinstance(decodificado, dict) and ("value" in decodificado or "valor" in decodificado):
                valor = decodificado.get("value", decodificado.get("valor"))
            else:
                valor = decodificado
        except json.JSONDecodeError:
            pass
        if rel == "plc/conexion":
            self.plc_edge = str(valor).strip().upper()
        elif rel == "estado/selector_remoto":
            self.selector_remoto = valor is True or str(valor).strip().lower() in ("true", "1", "on", "remoto")
        elif rel == "valvula/posicion_pct":
            try:
                self.posicion_valvula = float(valor)
            except (TypeError, ValueError):
                pass

    def _edge_fresco(self) -> bool:
        if self.edge_ultimo is None:
            return False
        return (datetime.now(timezone.utc) - self.edge_ultimo).total_seconds() <= TELEMETRIA_MAX_S

    def _leer_selector_remoto_plc(self):
        """Confirma el selector físico leyendo I:0/0 directamente; nunca escribe."""
        try:
            from pycomm3 import SLCDriver
            with SLCDriver(self.plc_ip) as plc:
                lectura = plc.read("I:0/0")
                if lectura.error:
                    return None
                return bool(lectura.value)
        except Exception as ex:  # noqa: BLE001
            self.log("PLC", f"no se pudo leer I:0/0: {ex}")
            return None

    def _leer_fuente_control_plc(self):
        """Lee el arbitraje PC/HMI. Nunca cambia B3:0/3 desde una orden web."""
        try:
            from pycomm3 import SLCDriver
            with SLCDriver(self.plc_ip) as plc:
                lectura = plc.read("B3:0/3")
                if lectura.error:
                    return None
                return "HMI" if bool(lectura.value) else "PC"
        except Exception as ex:  # noqa: BLE001
            self.log("PLC", f"no se pudo leer B3:0/3: {ex}")
            return None

    # ------------------------------------------------------------- validación
    def validar(self, orden: dict) -> str | None:
        equipo = str(orden.get("equipo") or EQUIPO).strip().lower()
        if equipo != EQUIPO:
            return "EQUIPO_INVALIDO"
        tipo = str(orden.get("tipo", "")).strip()
        if tipo not in TIPOS:
            return "TIPO_DESCONOCIDO"
        expira = orden.get("expira")
        if expira:
            try:
                if datetime.now(timezone.utc) > datetime.fromisoformat(str(expira)):
                    return "VENCIDA"
            except ValueError:
                return "EXPIRA_INVALIDA"
        if tipo == "Setpoint":
            unidad = str(orden.get("unidad") or "").strip().lower()
            if unidad != UNIDAD_SETPOINT:
                return "UNIDAD_INVALIDA"
            v = orden.get("valor")
            if not isinstance(v, (int, float)):
                return "RANGO_INVALIDO"
            lo, hi = RANGOS["Setpoint"]
            if v < lo or v > hi:
                return "RANGO_INVALIDO"
        if tipo == "ParametroPid":
            p = str(orden.get("parametro", "")).lower()
            v = orden.get("valor")
            if p not in RANGOS or not isinstance(v, (int, float)):
                return "RANGO_INVALIDO"
            lo, hi = RANGOS[p]
            if v < lo or v > hi:
                return "RANGO_INVALIDO"
        return None

    def validar_proceso(self) -> str | None:
        """Segunda validación con la telemetría real del edge (no aplica al simulador).
        En real es estricto; en dry-run solo rechaza con evidencia positiva de falla."""
        if self.modo == "simulador":
            return None
        if self.modo == "real":
            if not self._edge_fresco():
                return "TELEMETRIA_VENCIDA"
            if self.plc_edge != "CONECTADO":
                return "PLC_DESCONECTADO"
            if self.selector_remoto is not True:
                self.selector_remoto = self._leer_selector_remoto_plc()
                if self.selector_remoto is not True:
                    return "SELECTOR_NO_REMOTO"
            self.fuente_control = self._leer_fuente_control_plc()
            if self.fuente_control != "PC":
                return "CONTROL_EN_HMI" if self.fuente_control == "HMI" else "FUENTE_CONTROL_SIN_DATO"
            return None
        # dry-run: evidencia positiva de falla → rechazo; sin datos → se acepta (no escribe nada)
        if self._edge_fresco():
            if self.plc_edge == "DESCONECTADO":
                return "PLC_DESCONECTADO"
            if self.selector_remoto is False:
                return "SELECTOR_NO_REMOTO"
        return None

    def direccion_de(self, orden: dict) -> str | None:
        tipo = str(orden.get("tipo", ""))
        if tipo == "ParametroPid":
            return PID_POR_PARAMETRO.get(str(orden.get("parametro", "")).lower())
        return DIRECCION_POR_TIPO.get(tipo)

    # ------------------------------------------------------------- flujo cmd
    def procesar_cmd(self, mq: mqtt.Client, payload: str) -> None:
        try:
            orden = json.loads(payload)
        except json.JSONDecodeError:
            self.log("CMD", f"JSON inválido: {payload[:120]}")
            return

        oid = str(orden.get("id", ""))
        correlacion = orden.get("correlacion")
        self.log("CMD", f"recibida id={oid} tipo={orden.get('tipo')} valor={orden.get('valor')} "
                       f"unidad={orden.get('unidad')} correlacion={correlacion} modo_orden={orden.get('modo')}")

        # deduplicado local (además del del backend)
        if oid in self.vistos:
            self.log("CMD", f"id={oid} ya procesada localmente; se ignora")
            return
        self.vistos[oid] = time.time()
        while len(self.vistos) > 200:
            self.vistos.popitem(last=False)

        motivo = self.validar(orden) or self.validar_proceso()
        if motivo:
            self.ack(mq, oid, "RECHAZADO", motivo, correlacion=correlacion)
            return

        direccion = self.direccion_de(orden)
        nota = None
        if direccion is None:
            nota = "SIN_DIRECCION_CANDIDATA"
        elif es_direccion_prohibida(direccion):
            self.ack(mq, oid, "RECHAZADO", "DIRECCION_PROHIBIDA", correlacion=correlacion)
            return
        else:
            entrada = buscar_allowlist(direccion)
            if entrada is None:
                self.ack(mq, oid, "RECHAZADO", "DIRECCION_NO_PERMITIDA", correlacion=correlacion)
                return

        # ------------------------------------------------------ ejecución
        if self.modo == "real":
            ok, motivo_real, valor_esp = self.escribir_direccion_verificada(orden, direccion)
            if not ok:
                self.ack(mq, oid, "RECHAZADO", motivo_real, direccion=direccion, correlacion=correlacion)
                return
            self.ack(mq, oid, "ACEPTADO", None, direccion=direccion, escrito=False,
                     correlacion=correlacion, valor_esperado=valor_esp)
            self.ack(mq, oid, "ESCRITO", None, direccion=direccion, escrito=True,
                     correlacion=correlacion, valor_esperado=valor_esp)
            if str(orden.get("tipo")) in ("AbrirValvula", "CerrarValvula"):
                mq.publish(f"{FUNC}/valvula/posicion_pct", json.dumps({
                    "value": self.posicion_valvula, "unit": "%",
                    "source": "control-connector/calibracion-95s", "timestamp": ahora_iso(),
                }), qos=1, retain=True)
            # lectura posterior + comparación (solo sale CONFIRMADO si coincide)
            leido = self._releer(direccion)
            if leido is None:
                self.ack(mq, oid, "RECHAZADO", "SIN_LECTURA_POSTERIOR", direccion=direccion,
                         escrito=True, correlacion=correlacion, valor_esperado=valor_esp)
            elif abs(float(leido) - float(valor_esp)) > 1e-6:
                self.ack(mq, oid, "CONFIRMADO", None, direccion=direccion, escrito=True,
                         correlacion=correlacion, valor_esperado=valor_esp, valor_leido=float(leido),
                         detalle="lectura posterior NO coincide con el esperado (el backend marcará CONFIRMACION_NO_COINCIDE)")
            else:
                self.ack(mq, oid, "CONFIRMADO", None, direccion=direccion, escrito=True,
                         correlacion=correlacion, valor_esperado=valor_esp, valor_leido=float(leido),
                         detalle="lectura posterior coincide con el valor esperado")
            return

        # dry-run y simulador: jamás se invoca plc.write()
        etiqueta = "SIMULADOR" if self.modo == "simulador" else "DRY-RUN"
        self.ack(
            mq,
            oid,
            "ACEPTADO",
            None,
            direccion=direccion,
            escrito=False,
            correlacion=correlacion,
            detalle=f"{etiqueta}: validada, sin escritura ({nota or 'direccion candidata resuelta'})",
        )
        # el backend distingue CONFIRMADO (cierre): en dry-run/simulador el cierre es
        # "orden procesada sin escritura" (escrito=false). En real, CONFIRMADO exige lectura.
        self.ack(
            mq,
            oid,
            "CONFIRMADO",
            None,
            direccion=direccion,
            escrito=False,
            correlacion=correlacion,
            detalle=f"{etiqueta}: proceso completado sin escritura al PLC",
        )

    # ------------------------------------------------- escritura encapsulada (REAL)
    def escribir_direccion_verificada(self, orden: dict, direccion: str | None):
        """Único punto del proyecto que podría escribir. SIEMPRE rechaza mientras:
          modo != real · verificada == false · CONTROL_REAL != 1 · --habilitado-real ausente
          · selector REMOTO != true · dirección prohibida (O:0/O:1/I:/S:*).
        Los bits usan un pulso configurable (--pulso-ms): ON → espera → OFF, y se
        relee el bit para confirmar que volvió a cero. Devuelve (ok, motivo, valor_esperado).
        """
        if self.modo != "real":
            return False, "MODO_NO_REAL", None
        if not self.habilitado_real:
            return False, "REAL_NO_HABILITADO", None
        if os.environ.get("CONTROL_REAL") != "1":
            return False, "CONTROL_REAL_NO_DEFINIDO", None
        if direccion is None:
            return False, "SIN_DIRECCION_CANDIDATA", None
        if es_direccion_prohibida(direccion):
            return False, "DIRECCION_PROHIBIDA", None
        entrada = buscar_allowlist(direccion)
        if entrada is None:
            return False, "DIRECCION_NO_PERMITIDA", None
        if not entrada["verificada"]:
            return False, "NO_VERIFICADAS", None     # hoy: las 13 direcciones
        if self.selector_remoto is not True:
            return False, "SELECTOR_NO_REMOTO", None

        try:
            from pycomm3 import SLCDriver  # import diferido: solo en real
        except Exception:
            return False, "PYCOMM3_NO_DISPONIBLE", None

        es_bit = entrada["tipo"] == "bit"
        modo_escritura = entrada.get("escritura", "pulso")
        tipo_cmd = str(orden.get("tipo", ""))
        valor = orden.get("valor")
        if es_bit:
            # Bits de NIVEL (p.ej. START_PC B3:0/4) se MANTIENEN: el ladder exige que
            # START_PC quede en 1 mientras se quiera marcha (sello en serie, rung 0005).
            # Bits de PULSO vuelven a cero tras --pulso-ms (solo tras validacion en lab).
            valor_codificado = VALOR_POR_COMANDO.get(tipo_cmd, 1)
        elif tipo_cmd == "Setpoint" and isinstance(valor, (int, float)):
            valor_codificado = int(round(16348 - 400 * float(valor)))
        elif tipo_cmd == "ParametroPid" and isinstance(valor, (int, float)):
            valor_codificado = int(round(100 * float(valor)))
        elif isinstance(valor, (int, float)):
            valor_codificado = int(valor)
        else:
            return False, "VALOR_INVALIDO", None

        try:
            from pycomm3 import SLCDriver  # import diferido: solo en real
        except Exception:
            return False, "PYCOMM3_NO_DISPONIBLE", None

        try:
            with SLCDriver(self.plc_ip) as plc:
                # selector fisico en REMOTO con lectura fresca antes de tocar nada
                remoto = plc.read("I:0/0")
                if not bool(remoto):
                    return False, "SELECTOR_NO_REMOTO", None
                fuente = plc.read("B3:0/3")
                if fuente.error:
                    return False, "FUENTE_CONTROL_SIN_DATO", None
                self.fuente_control = "HMI" if bool(fuente.value) else "PC"
                if self.fuente_control != "PC":
                    return False, "CONTROL_EN_HMI", None
                if tipo_cmd in ("AbrirValvula", "CerrarValvula"):
                    marcha = plc.read("O:0/2")
                    if marcha.error or bool(marcha.value):
                        return False, "BOMBA_DEBE_ESTAR_DETENIDA", None
                    destino = 100.0 if tipo_cmd == "AbrirValvula" else 80.0
                    delta = destino - self.posicion_valvula
                    centesimas = int(round(abs(delta) * 95.0))
                    if centesimas > 0:
                        plc.write(("N7:1", centesimas if delta > 0 else 0))
                        plc.write(("N7:2", centesimas if delta < 0 else 0))
                        plc.write(("B3:0/13", True))
                        time.sleep(0.5)
                        plc.write(("B3:0/13", False))
                        time.sleep(centesimas / 100.0 + 1.0)
                        salidas = plc.read("O:0/4", "O:0/5")
                        if any(x.error or bool(x.value) for x in salidas):
                            return False, "VALVULA_MOVIMIENTO_NO_FINALIZO", None
                    self.posicion_valvula = destino
                    return True, None, 0.0
                anterior = plc.read(direccion)
                self.log("REAL", f"write {direccion} = {valor_codificado} "
                                f"(anterior={anterior.value} modo_escritura={modo_escritura})")
                plc.write((direccion, valor_codificado))
                if es_bit and modo_escritura == "pulso":
                    # pulso: nunca mantener un bit activo si el ladder lo exige asi
                    time.sleep(max(self.pulso_ms, 50) / 1000.0)
                    plc.write((direccion, 0))
                    final = plc.read(direccion)
                    if bool(final.value):
                        return False, "PULSO_NO_CERRO", None
                    self.log("REAL", f"pulso {direccion} completado (volvio a 0)")
                elif es_bit and modo_escritura == "nivel" and int(valor_codificado) == 1:
                    # mantener: verificar que el bit quedo en 1 (sin devolverlo a 0)
                    final = plc.read(direccion)
                    if not bool(final.value):
                        return False, "NIVEL_NO_SE_MANTUVO", None
                    self.log("REAL", f"nivel {direccion} mantenido en 1 (sin pulso)")
                return True, None, float(valor_codificado)
        except Exception as ex:  # noqa: BLE001 - informa al operador
            return False, f"PLC_ERROR:{ex}", None

    def _releer(self, direccion: str):
        """Lectura posterior para la confirmación (solo modo real)."""
        try:
            from pycomm3 import SLCDriver
            with SLCDriver(self.plc_ip) as plc:
                r = plc.read(direccion)
                return None if r.error else float(r.value)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------- salidas
    def ack(self, mq, oid, estado, motivo=None, direccion=None, escrito=False, detalle=None,
            correlacion=None, valor_esperado=None, valor_leido=None) -> None:
        cuerpo = {
            "id": oid,
            "estado": estado,
            "motivo": motivo,
            "modo": self.etiqueta(),
            "direccion": direccion,
            "escrito": escrito,
            "correlacion": correlacion,
            "valor_esperado": valor_esperado,
            "valor_leido": valor_leido,
            "detalle": detalle,
            "ts": ahora_iso(),
        }
        self.ultimo_ack = cuerpo
        self.procesadas += 1
        self.log("ACK", f"{estado} motivo={motivo} direccion={direccion} escrito={escrito} "
                       f"leido={valor_leido} correlacion={correlacion}")
        mq.publish(f"{CTRL}/ack", json.dumps(cuerpo), qos=1)

    def publicar_state(self, mq) -> None:
        if self.modo == "real":
            remoto = self._leer_selector_remoto_plc()
            if remoto is not None:
                self.selector_remoto = remoto
                ts = ahora_iso()
                mq.publish(f"{FUNC}/estado/selector_remoto", json.dumps({"value": remoto, "source": "control-connector/I:0/0", "timestamp": ts}), qos=1)
                mq.publish(f"{FUNC}/estado/selector_local", json.dumps({"value": not remoto, "source": "control-connector/I:0/0", "timestamp": ts}), qos=1)
                fuente = self._leer_fuente_control_plc()
                if fuente is not None:
                    self.fuente_control = fuente
                    mq.publish(f"{FUNC}/estado/fuente_control", json.dumps({
                        "value": fuente, "source": "control-connector/B3:0/3",
                        "timestamp": ts,
                    }), qos=1, retain=True)
                mq.publish(f"{FUNC}/valvula/posicion_pct", json.dumps({
                    "value": self.posicion_valvula, "unit": "%",
                    "source": "control-connector/calibracion-95s", "timestamp": ts,
                }), qos=1, retain=True)
        mq.publish(f"{CTRL}/state", json.dumps(self.estado()), qos=1)


def crear_cliente(host: str, puerto: int, conector: Conector) -> mqtt.Client:
    try:
        mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ctrl-ml1100-{socket.gethostname()}")
    except AttributeError:  # paho 1.x
        mq = mqtt.Client(client_id=f"ctrl-ml1100-{socket.gethostname()}")

    def on_connect(client, userdata, flags, reason_code, properties=None):
        client.subscribe(f"{CTRL}/cmd", qos=1)
        client.subscribe(f"{FUNC}/#", qos=1)   # telemetría del edge: doble validación
        conector.log("MQTT", f"conectado; suscrito a {CTRL}/cmd y {FUNC}/#")

    def on_message(client, userdata, msg):
        topico = msg.topic
        payload = msg.payload.decode("utf-8", "replace")
        if topico.startswith(f"{CTRL}/cmd"):
            conector.procesar_cmd(client, payload)
        elif topico.startswith(FUNC):
            conector.registrar_edge(topico, payload)

    mq.on_connect = on_connect
    mq.on_message = on_message
    mq.connect(host, puerto, keepalive=30)
    mq.loop_start()
    return mq


def _lanzar_salud(conector: "Conector", puerto: int) -> None:
    """Health HTTP minimalista para el healthcheck de Docker (solo lectura de estado)."""

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path != "/healthz":
                self.send_response(404)
                self.end_headers()
                return
            cuerpo = json.dumps({"status": "ok", **conector.estado()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    threading.Thread(
        target=lambda: ThreadingHTTPServer(("0.0.0.0", puerto), _H).serve_forever(),
        daemon=True,
    ).start()


def main() -> int:
    ap = argparse.ArgumentParser(description="Conector de CONTROL nivel-mcn09 (dry-run por defecto; sin escrituras al PLC)")
    ap.add_argument("--modo", choices=["dry-run", "simulador", "real"], default="dry-run")
    ap.add_argument("--broker", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=1883)
    ap.add_argument("--plc", default="192.168.114.9")
    ap.add_argument("--habilitado-real", action="store_true", help="segundo interruptor del triple gate (el resto: env CONTROL_REAL=1 + selector REMOTO + direcciones VERIFICADAS)")
    ap.add_argument("--pulso-ms", type=int, default=500, help="duración del pulso de bits de arranque/parada (solo modo real)")
    a = ap.parse_args()

    conector = Conector(a.modo, a.plc, a.habilitado_real, a.pulso_ms)
    salud_puerto = int(os.environ.get("CONECTOR_SALUD_PUERTO", "8098"))
    _lanzar_salud(conector, salud_puerto)
    print("=" * 78, flush=True)
    print(f"  CONECTOR DE CONTROL · MODO: {conector.etiqueta()}", flush=True)
    print("  · dry-run/simulador: NUNCA escribe en el PLC (no se llama plc.write)", flush=True)
    print("  · real: triple gate + allowlist VERIFICADA; salidas O:0/O:1/I:/S: prohibidas", flush=True)
    print(f"  · allowlist: {sum(1 for e in ALLOWLIST if e['verificada'])}/{len(ALLOWLIST)} direcciones VERIFICADAS (resto NO_VERIFICADAS)", flush=True)
    print(f"  · doble validación con telemetría del edge (suscripción {FUNC}/#)", flush=True)
    print("=" * 78, flush=True)

    mq = crear_cliente(a.broker, a.puerto, conector)
    ultimo_state = 0.0
    try:
        while True:
            if time.time() - ultimo_state >= 15:
                conector.publicar_state(mq)
                ultimo_state = time.time()
            time.sleep(0.5)
    except KeyboardInterrupt:
        conector.log("MQTT", "interrumpido por el operador")
    finally:
        mq.loop_stop()
        mq.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
