"""
Conector edge S7-200 (CP243-1) -> MQTT (UNS), con control condicionado. v3.2

Requiere la IP local 192.168.114.70, autorizada en el enlace 0 del CP243-1 (TSAP 1000).
El enlace 1 (TSAP 11.00) apunta a .10, direccion ocupada por el PLC Twido de temperatura.

Mapa de variables tomado del proyecto oficial de PC Access (OPC_caudal.pca, Inducontrol)
y de la tabla del lazo PID identificada por exploracion (VB159, 36 bytes).
Calibracion del caudalimetro Kobold DRG (calibracion_caudalimetro.xls, 13 puntos, R2=0.9997):
    Q[L/min] = 0.005498 * AIW0 - 34.896      (4-20 mA -> 0-141 L/min)
    Q[L/min] = 140 * PV_norm                 (convencion del programa: SETPOINT VD400 / 140 = SP del PID)
    Nota: el CP243-1 rechaza leer AIW/AQW directamente (error 0x03). Se usan copias en memoria:
      AIW0 -> MW3 (Network 11, valida en REMOTO), AIW2 -> MW2 (Network 21, valida en LOCAL),
      AQW0 <- MW25 (valvula aplicada), AQW2 <- VW8 (variador aplicado).
    En modo LOCAL el potenciometro (MW2) gobierna el caudal y la salida del PID no se aplica.

Cambios v3.2 (19-oct-2026):
  - pid/ki y pid/kd eran en realidad Ti y Td (tabla del lazo VB159): ahora pid/ti y pid/td [min]; pid/kp -> pid/kc (VD171).
  - Nuevo caudal/caudalimetro (MW3 + calibracion): segunda medida independiente del caudal.
  - Variador y valvula: se publica lo aplicado (VW8, MW25) en %, mismos topicos que los historicos .lvm.
  - Potenciometro (MW2) y caudalimetro (MW3) solo se publican en el modo donde son validos.

La escritura solo se acepta con CONTROL_CAUDAL_REAL=1, selector REMOTO y mando PC.

Instalacion:  pip install python-snap7 paho-mqtt
Uso:          python conector_edge_s7200.py
"""
import argparse
import json
import socket
import os
import threading
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
import snap7
from snap7.connection import ISOTCPConnection
from snap7.s7protocol import S7WordLen
from snap7.type import Area
from snap7.util import get_bool, get_int, get_real, set_bool, set_int, set_real

BASE = "uss/campus/lab-automatizacion/sl01la07/caudal-mcc09"
CONTROL = BASE + "/control"
TZ_LIMA = timezone(timedelta(hours=-5))


class SourceBoundISOTCPConnection(ISOTCPConnection):
    """Open the S7 socket from the client IP authorized by the CP243-1."""

    source_ip = None

    def _tcp_connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.socket.settimeout(self.timeout)
        if self.source_ip:
            self.socket.bind((self.source_ip, 0))
        self.socket.connect((self.host, self.port))

AREA_AI, AREA_AQ = 0x06, 0x07  # entradas/salidas analogicas del S7-200 (protocolo S7)


FONDO_ESCALA_LPM = 140.0  # el programa del PLC normaliza con 140 L/min (VD400 / 140 = SP del PID)

CONTROL_MAPA = {
    "Iniciar": ("M", 0, "bool", 2), "Detener": ("M", 0, "bool", 2),
    "Setpoint": ("V", 400, "real", None), "AjustarValvula": ("M", 25, "int", None),
    "kc": ("V", 100, "real", None), "ti": ("V", 108, "real", None), "td": ("V", 116, "real", None),
}


def q_desde_norm(x):
    return round(FONDO_ESCALA_LPM * x, 3)


def q_desde_aiw(x):
    return round(0.005498 * x - 34.896, 3)


def pct_de_cuentas(x):
    """Salidas analogicas del S7-200: 0-32000 cuentas = 0-100 %."""
    return round(x / 320.0, 2)


def en_remoto(c):
    return c.get("LOCAL") is False


def en_local(c):
    return c.get("LOCAL") is True


# area: V, M, I, Q, AI, AQ | tipo: real, int, bool
# "valido": condicion sobre la lectura del mismo ciclo; si es False la variable no se publica.
#   MW2 y MW3 comparten el byte MB3 (Network 11: AIW0 -> MW3 en cada ciclo; Network 21: AIW2 -> MW2 solo en LOCAL).
#   - En REMOTO, MW3 = AIW0 intacto (caudalimetro crudo) y MW2 es basura (su byte bajo es el alto de AIW0).
#   - En LOCAL, MW2 = AIW2 (potenciometro) y MW3 queda corrompido.
TAGS = [
    # --- Proceso ---
    {"n": "PID_PV", "dir": "VD159", "area": "V", "off": 159, "tipo": "real", "topic": "caudal/pv_pid", "unidad": "L/min",
     "conv": q_desde_norm, "desc": "Caudal medido segun el lazo PID (PV normalizada x 140)"},
    {"n": "CAUDALIMETRO_RAW", "dir": "MW3", "area": "M", "off": 3, "tipo": "int", "topic": "caudal/caudalimetro_raw",
     "unidad": "cuentas", "valido": en_remoto, "desc": "Copia de AIW0 (Kobold DRG 4-20 mA); valida solo en modo REMOTO"},
    {"n": "CAUDALIMETRO", "dir": "MW3", "area": "M", "off": 3, "tipo": "int", "topic": "caudal/caudalimetro", "unidad": "L/min",
     "conv": q_desde_aiw, "valido": en_remoto,
     "desc": "Caudal por calibracion del caudalimetro (0.005498*AIW0-34.896); medida independiente de la PV del PID"},
    {"n": "PID_SP", "dir": "VD163", "area": "V", "off": 163, "tipo": "real", "topic": "caudal/setpoint_pid", "unidad": "L/min",
     "conv": q_desde_norm, "desc": "Setpoint efectivo del lazo PID"},
    {"n": "SETPOINT", "dir": "VD400", "area": "V", "off": 400, "tipo": "real", "topic": "caudal/setpoint", "unidad": "L/min",
     "desc": "Setpoint remoto (PC/SCADA)"},
    {"n": "SETPOINT_HMI", "dir": "VD408", "area": "V", "off": 408, "tipo": "real", "topic": "caudal/setpoint_hmi", "unidad": "L/min",
     "desc": "Setpoint desde la HMI (se usa cuando M0.6 = modo HMI)"},
    # --- Actuadores (valores aplicados realmente a las salidas analogicas) ---
    {"n": "VARIADOR", "dir": "VW8", "area": "V", "off": 8, "tipo": "int", "topic": "actuadores/variador_pct", "unidad": "%",
     "conv": pct_de_cuentas, "desc": "Consigna aplicada al variador (VW8 -> AQW2): salida PID en remoto, potenciometro en local"},
    {"n": "VALVULA", "dir": "MW25", "area": "M", "off": 25, "tipo": "int", "topic": "actuadores/valvula_pct", "unidad": "%",
     "conv": pct_de_cuentas, "desc": "Apertura aplicada a la valvula proporcional (MW25 -> AQW0); 100 % en local"},
    {"n": "POTENCIOMETRO", "dir": "MW2", "area": "M", "off": 2, "tipo": "int", "topic": "actuadores/potenciometro", "unidad": "cuentas",
     "valido": en_local, "desc": "Potenciometro del tablero (copia de AIW2); valido solo en modo LOCAL"},
    {"n": "PID_SALIDA", "dir": "VD167", "area": "V", "off": 167, "tipo": "real", "topic": "pid/salida", "unidad": "%",
     "conv": lambda x: round(100 * x, 2), "desc": "Salida calculada por el PID (Mn)"},
    # --- Estado ---
    {"n": "SISTEMA_FUNCIONANDO", "dir": "Q0.2", "area": "Q", "off": 0, "bit": 2, "tipo": "bool", "topic": "estado/sistema_funcionando",
     "desc": "Bomba/sistema en marcha"},
    {"n": "NIVEL_ALTO", "dir": "Q0.0", "area": "Q", "off": 0, "bit": 0, "tipo": "bool", "topic": "estado/nivel_alto",
     "desc": "Indicador de nivel alto del tanque"},
    {"n": "NIVEL_BAJO", "dir": "Q0.1", "area": "Q", "off": 0, "bit": 1, "tipo": "bool", "topic": "estado/nivel_bajo",
     "desc": "Indicador de nivel bajo del tanque (Q0.1 = NOT I0.2)"},
    {"n": "REMOTO", "dir": "I0.0", "area": "I", "off": 0, "bit": 0, "tipo": "bool", "topic": "estado/selector_remoto",
     "desc": "Selector en REMOTO (control por PID)"},
    {"n": "LOCAL", "dir": "I0.1", "area": "I", "off": 0, "bit": 1, "tipo": "bool", "topic": "estado/selector_local",
     "desc": "Selector en LOCAL (control por potenciometro)"},
    {"n": "START_REMOTO", "dir": "M0.2", "area": "M", "off": 0, "bit": 2, "tipo": "bool", "topic": "estado/start_remoto",
     "desc": "Orden de arranque remota"},
    {"n": "HMI_PC", "dir": "M0.3", "area": "M", "off": 0, "bit": 3, "tipo": "bool", "topic": "estado/modo_hmi_pc",
     "desc": "1 = mando desde HMI, 0 = mando desde PC"},
    # --- E/S sin documentar (relevamiento de LEDs 10-nov-2026: I0.5 y Q1.1 encendidos con la bomba en marcha).
    #     Solo lectura, mismos bytes IB0/QB0-QB1 que ya se leen: sirven para identificar en campo
    #     guardamotor, paro de emergencia, piloto de marcha, etc. ---
    {"n": "I0_3", "dir": "I0.3", "area": "I", "off": 0, "bit": 3, "tipo": "bool", "topic": "io/i0_3", "estado": "hipotesis", "desc": "Entrada sin documentar"},
    {"n": "I0_4", "dir": "I0.4", "area": "I", "off": 0, "bit": 4, "tipo": "bool", "topic": "io/i0_4", "estado": "hipotesis", "desc": "Entrada sin documentar"},
    {"n": "I0_5", "dir": "I0.5", "area": "I", "off": 0, "bit": 5, "tipo": "bool", "topic": "io/i0_5", "estado": "hipotesis", "desc": "Entrada sin documentar, siempre ON. NO es el guardamotor (10-nov: no cambio con el GV2 en STOP); candidata: contacto OF del C60H o paro de emergencia"},
    {"n": "I0_6", "dir": "I0.6", "area": "I", "off": 0, "bit": 6, "tipo": "bool", "topic": "io/i0_6", "estado": "hipotesis", "desc": "Entrada sin documentar"},
    {"n": "I0_7", "dir": "I0.7", "area": "I", "off": 0, "bit": 7, "tipo": "bool", "topic": "io/i0_7", "estado": "hipotesis", "desc": "Entrada sin documentar"},
    {"n": "Q0_3", "dir": "Q0.3", "area": "Q", "off": 0, "bit": 3, "tipo": "bool", "topic": "io/q0_3", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q0_4", "dir": "Q0.4", "area": "Q", "off": 0, "bit": 4, "tipo": "bool", "topic": "io/q0_4", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q0_5", "dir": "Q0.5", "area": "Q", "off": 0, "bit": 5, "tipo": "bool", "topic": "io/q0_5", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q0_6", "dir": "Q0.6", "area": "Q", "off": 0, "bit": 6, "tipo": "bool", "topic": "io/q0_6", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q0_7", "dir": "Q0.7", "area": "Q", "off": 0, "bit": 7, "tipo": "bool", "topic": "io/q0_7", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q1_0", "dir": "Q1.0", "area": "Q", "off": 1, "bit": 0, "tipo": "bool", "topic": "io/q1_0", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q1_1", "dir": "Q1.1", "area": "Q", "off": 1, "bit": 1, "tipo": "bool", "topic": "io/q1_1", "estado": "confirmado", "desc": "Orden de marcha (RUN) al variador Altivar 11: sigue a Q0.2 (verificado 10-nov con Detener/Iniciar)"},
    {"n": "Q1_2", "dir": "Q1.2", "area": "Q", "off": 1, "bit": 2, "tipo": "bool", "topic": "io/q1_2", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q1_3", "dir": "Q1.3", "area": "Q", "off": 1, "bit": 3, "tipo": "bool", "topic": "io/q1_3", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q1_4", "dir": "Q1.4", "area": "Q", "off": 1, "bit": 4, "tipo": "bool", "topic": "io/q1_4", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q1_5", "dir": "Q1.5", "area": "Q", "off": 1, "bit": 5, "tipo": "bool", "topic": "io/q1_5", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q1_6", "dir": "Q1.6", "area": "Q", "off": 1, "bit": 6, "tipo": "bool", "topic": "io/q1_6", "estado": "hipotesis", "desc": "Salida sin documentar"},
    {"n": "Q1_7", "dir": "Q1.7", "area": "Q", "off": 1, "bit": 7, "tipo": "bool", "topic": "io/q1_7", "estado": "hipotesis", "desc": "Salida sin documentar"},
    # --- Sintonia PID (tabla del lazo en VB159; formato S7-200: Kc, Ts, Ti, Td, Mx) ---
    {"n": "KC", "dir": "VD171", "area": "V", "off": 171, "tipo": "real", "topic": "pid/kc",
     "desc": "Ganancia proporcional Kc del lazo"},
    {"n": "TI", "dir": "VD179", "area": "V", "off": 179, "tipo": "real", "topic": "pid/ti", "unidad": "min",
     "desc": "Tiempo integral Ti (no es una ganancia Ki)"},
    {"n": "TD", "dir": "VD183", "area": "V", "off": 183, "tipo": "real", "topic": "pid/td", "unidad": "min",
     "desc": "Tiempo derivativo Td (no es una ganancia Kd)"},
    {"n": "PID_TS", "dir": "VD175", "area": "V", "off": 175, "tipo": "real", "topic": "pid/ts", "unidad": "s",
     "desc": "Tiempo de muestreo del lazo"},
    {"n": "PID_MX", "dir": "VD187", "area": "V", "off": 187, "tipo": "real", "topic": "pid/mx", "unidad": "fraccion 0-1",
     "desc": "Bias / suma integral del lazo"},
]

TAMANO = {"real": 4, "int": 2, "bool": 1}


def ahora():
    return datetime.now(TZ_LIMA).isoformat(timespec="milliseconds")   # ms: para medir la latencia PLC → backend


class LectorPLC:
    def __init__(self, ip, local_tsap, remote_tsap, db_v, puerto=102):
        self.ip, self.local_tsap, self.remote_tsap, self.db_v, self.puerto = ip, local_tsap, remote_tsap, db_v, puerto
        self.c = None
        self.analogicas_ok = True  # se desactiva si el CP243-1 no acepta AIW/AQW
        self.lock = threading.RLock()

    def conectar(self):
        c = snap7.client.Client()
        c.set_connection_params(self.ip, self.local_tsap, self.remote_tsap)
        c._connect(self.ip, 0, 0, self.puerto)  # usa los TSAP fijados; connect() los reemplazaria
        self.c = c

    def desconectar(self):
        if self.c:
            try:
                self.c.disconnect()
            except Exception:
                pass
        self.c = None

    def _leer_crudo(self, area_code, start, size):
        """Lectura S7 de un area sin equivalente en snap7 (AIW/AQW del S7-200)."""
        def req():
            return self.c.protocol.build_read_request(
                area=area_code, db_number=0, start=start, word_len=S7WordLen.BYTE, count=size)
        resp = self.c._send_receive_with_reconnect(req)
        return bytearray(self.c.protocol.extract_read_data(resp, S7WordLen.BYTE, size))

    def _leer_bloque(self, area, ini, fin):
        n = fin - ini
        if area == "V":
            data = bytearray()
            pos = ini
            while pos < fin:
                k = min(100, fin - pos)
                data += self.c.db_read(self.db_v, pos, k)
                pos += k
            return data
        if area == "M":
            return self.c.read_area(Area.MK, 0, ini, n)
        if area == "I":
            return self.c.read_area(Area.PE, 0, ini, n)
        if area == "Q":
            return self.c.read_area(Area.PA, 0, ini, n)
        if area in ("AI", "AQ"):
            return self._leer_crudo(AREA_AI if area == "AI" else AREA_AQ, ini, n)
        raise ValueError(area)

    def leer(self, tags):
        """Agrupa por area y rangos contiguos (huecos < 32 bytes) para minimizar peticiones."""
        out = {}
        por_area = {}
        for t in tags:
            if t["area"] in ("AI", "AQ") and not self.analogicas_ok:
                continue
            por_area.setdefault(t["area"], []).append(t)
        for area, lista in por_area.items():
            lista = sorted(lista, key=lambda t: t["off"])
            grupos, actual = [], [lista[0]]
            for t in lista[1:]:
                fin_prev = max(x["off"] + TAMANO[x["tipo"]] for x in actual)
                if t["off"] - fin_prev < 32:
                    actual.append(t)
                else:
                    grupos.append(actual)
                    actual = [t]
            grupos.append(actual)
            for g in grupos:
                ini = min(t["off"] for t in g)
                fin = max(t["off"] + TAMANO[t["tipo"]] for t in g)
                try:
                    data = self._leer_bloque(area, ini, fin)
                except Exception as e:
                    if area in ("AI", "AQ"):
                        self.analogicas_ok = False
                        print(f"[{ahora()}] El CP243-1 no acepta lectura directa de {area}: {e}. "
                              "Se omite; el caudal sale de la PV del PID.")
                        continue
                    raise
                for t in g:
                    o = t["off"] - ini
                    if t["tipo"] == "real":
                        out[t["n"]] = get_real(data, o)
                    elif t["tipo"] == "int":
                        out[t["n"]] = get_int(data, o)
                    else:
                        out[t["n"]] = get_bool(data, o, t["bit"])
        return out

    def leer_memoria(self, area, off, tipo, bit=None):
        with self.lock:
            size = 1 if tipo == "bool" else 2 if tipo == "int" else 4
            if area == "V": data = self.c.db_read(self.db_v, off, size)
            elif area == "M": data = self.c.read_area(Area.MK, 0, off, size)
            elif area == "I": data = self.c.read_area(Area.PE, 0, off, size)
            else: data = self.c.read_area(Area.PA, 0, off, size)
            return get_bool(data, 0, bit) if tipo == "bool" else get_int(data, 0) if tipo == "int" else get_real(data, 0)

    def escribir_memoria(self, area, off, tipo, valor, bit=None):
        """Único punto de escritura: exclusivamente M/V; nunca I/Q/AI/AQ."""
        if area not in ("M", "V"): raise ValueError("DIRECCION_PROHIBIDA")
        with self.lock:
            size = 1 if tipo == "bool" else 2 if tipo == "int" else 4
            data = self.c.db_read(self.db_v, off, size) if area == "V" else self.c.read_area(Area.MK, 0, off, size)
            if tipo == "bool": set_bool(data, 0, bit, bool(valor))
            elif tipo == "int": set_int(data, 0, int(valor))
            else: set_real(data, 0, float(valor))
            if area == "V": self.c.db_write(self.db_v, off, data)
            else: self.c.write_area(Area.MK, 0, off, data)
            time.sleep(.2)
            return self.leer_memoria(area, off, tipo, bit)


def main():
    p = argparse.ArgumentParser(description="Conector S7-200 -> MQTT (solo lectura)")
    p.add_argument("--plc", default="192.168.114.7")
    p.add_argument("--source-ip", default=None, help="IP local autorizada por el CP243-1")
    p.add_argument("--local-tsap", default="1100")
    p.add_argument("--remote-tsap", default="1100")
    p.add_argument("--puerto-plc", type=int, default=102, help="puerto S7 (102 en el PLC real; el simulador usa 1102)")
    p.add_argument("--db-v", type=int, default=1)
    p.add_argument("--broker", default="localhost")
    p.add_argument("--puerto", type=int, default=1883)
    p.add_argument("--periodo", type=float, default=1.0)
    p.add_argument("--max-silencio", type=float, default=60.0, help="Publicar al menos cada N s")
    a = p.parse_args()
    SourceBoundISOTCPConnection.source_ip = a.source_ip
    snap7.client.ISOTCPConnection = SourceBoundISOTCPConnection
    socket.setdefaulttimeout(5)

    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"edge-s7200-{socket.gethostname()}")
    mq.will_set(f"{BASE}/funcional/edge/estado", "OFFLINE", qos=1, retain=True)
    mq.reconnect_delay_set(1, 10)

    def al_conectar(client, userdata, *args):
        # Se ejecuta en CADA (re)conexion: sin esto, tras un corte del broker (PC suspendida,
        # broker reiniciado) paho reconecta pero sin la suscripcion a /cmd -> ordenes en Timeout.
        client.subscribe(f"{CONTROL}/cmd", qos=1)
        client.publish(f"{BASE}/funcional/edge/estado", "ONLINE", qos=1, retain=True)
        client.publish(f"{CONTROL}/state", json.dumps({"modo": "REAL" if os.getenv("CONTROL_CAUDAL_REAL") == "1" else "BLOQUEADO", "ts": ahora()}), qos=1, retain=True)
        print(f"[{ahora()}] MQTT conectado: escuchando ordenes en {CONTROL}/cmd", flush=True)

    def al_desconectar(client, userdata, *args):
        print(f"[{ahora()}] MQTT desconectado: reintentando...", flush=True)

    mq.on_connect, mq.on_disconnect = al_conectar, al_desconectar
    mq.connect(a.broker, a.puerto, keepalive=30)
    mq.loop_start()
    mq.publish(f"{BASE}/funcional/edge/estado", "ONLINE", qos=1, retain=True)
    # AIW/AQW no son accesibles por el CP243-1 (error 0x03 confirmado): no se anuncian en el catalogo.
    catalogo = [{**{k: v for k, v in t.items() if k not in ("conv", "valido")},
                 **({"condicion": "solo REMOTO" if t["valido"] is en_remoto else "solo LOCAL"} if "valido" in t else {})}
                for t in TAGS if t["area"] not in ("AI", "AQ")]
    mq.publish(f"{BASE}/descriptivo/variables", json.dumps(catalogo, ensure_ascii=False), qos=1, retain=True)
    mq.publish(f"{BASE}/descriptivo/equipo", json.dumps({
        "plc": "S7-200 CPU226", "modulo_eth": "CP243-1", "ip": a.plc,
        "caudalimetro": "Kobold DRG, 4-20 mA, 0-141 L/min (calibrado)",
        "fuente_mapa": "OPC_caudal.pca (S7-200 PC Access, Inducontrol)"}, ensure_ascii=False), qos=1, retain=True)

    plc = LectorPLC(a.plc, int(a.local_tsap, 16), int(a.remote_tsap, 16), a.db_v, a.puerto_plc)

    def ack(oid, estado, **extra):
        mq.publish(f"{CONTROL}/ack", json.dumps({"id": oid, "estado": estado, "ts": ahora(), **extra}), qos=1)

    def control_recibido(client, userdata, msg):
        if msg.topic != f"{CONTROL}/cmd": return
        try:
            orden = json.loads(msg.payload.decode("utf-8")); oid = str(orden["id"]); tipo = str(orden["tipo"])
        except Exception:
            return
        try:
            if os.getenv("CONTROL_CAUDAL_REAL") != "1": raise PermissionError("REAL_NO_ARMADO")
            if plc.c is None: raise ConnectionError("PLC_DESCONECTADO")
            remoto = plc.leer_memoria("I", 0, "bool", 0)
            local = plc.leer_memoria("I", 0, "bool", 1)
            mando_hmi = plc.leer_memoria("M", 0, "bool", 3)
            if not remoto or local: raise PermissionError("SELECTOR_NO_REMOTO")
            if mando_hmi: raise PermissionError("CONTROL_EN_HMI")
            if tipo == "Iniciar" and plc.leer_memoria("Q", 0, "bool", 1): raise PermissionError("NIVEL_BAJO_T1")
            if tipo == "Iniciar" and plc.leer_memoria("Q", 0, "bool", 0): raise PermissionError("NIVEL_ALTO_T1")
            clave = str(orden.get("parametro", "")).lower() if tipo == "ParametroPid" else tipo
            spec = CONTROL_MAPA.get(clave)
            if spec is None: raise PermissionError("DIRECCION_NO_PERMITIDA")
            valor = 1 if tipo == "Iniciar" else 0 if tipo == "Detener" else orden.get("valor")
            if tipo == "Setpoint" and (not isinstance(valor, (int, float)) or not 0 <= valor <= 140): raise ValueError("RANGO_INVALIDO")
            if tipo == "AjustarValvula":
                if not isinstance(valor, (int, float)) or not 0 <= valor <= 100: raise ValueError("RANGO_INVALIDO")
                valor = round(valor * 320)
            ack(oid, "Aceptado", escrito=False)
            area, off, clase, bit = spec
            if tipo == "AjustarValvula":
                actual, destino = int(plc.leer_memoria(area, off, clase, bit)), int(valor)
                while actual != destino:
                    actual += max(-320, min(320, destino - actual))
                    plc.escribir_memoria(area, off, clase, actual, bit); time.sleep(.1)
                leido, tolerancia = plc.leer_memoria(area, off, clase, bit), 1
            else:
                leido = plc.escribir_memoria(area, off, clase, valor, bit); tolerancia = .001 if clase == "real" else 0
            ack(oid, "Escrito", escrito=True, valor_esperado=valor)
            if abs(float(leido) - float(valor)) <= tolerancia:
                ack(oid, "Confirmado", escrito=True, valor_esperado=valor, valor_leido=leido)
            else: ack(oid, "Error", motivo="CONFIRMACION_NO_COINCIDE", escrito=True, valor_esperado=valor, valor_leido=leido)
        except (PermissionError, ValueError, ConnectionError) as e:
            ack(oid, "Rechazado", motivo=str(e), escrito=False)
        except Exception as e:
            ack(oid, "Error", motivo=f"PLC_ERROR:{e}", escrito=False)

    mq.on_message = control_recibido   # la suscripcion a /cmd la hace al_conectar (en cada reconexion)
    ultimo, ultimo_latido = {}, 0.0
    print(f"Publicando en mqtt://{a.broker}:{a.puerto}/{BASE}/... (Ctrl+C para detener)")

    # --- WATCHDOG: si el ciclo principal se congela (p. ej. al desconectar el cable de red
    # el socket S7 puede quedar colgado), el proceso se cierra solo y el lanzador
    # launch_caudal_edge.ps1 lo vuelve a arrancar en 5 s con una sesion S7 nueva. ---
    latido = {"t": time.time()}
    def vigilante():
        while True:
            time.sleep(5)
            parado = time.time() - latido["t"]
            if parado > 45:
                print(f"[{ahora()}] WATCHDOG: ciclo congelado {parado:.0f} s -> reinicio el conector", flush=True)
                try:
                    mq.publish(f"{BASE}/funcional/plc/conexion", "SIN_CONEXION", qos=1, retain=True)
                    time.sleep(0.5)   # no se llama a desconectar(): un socket colgado podria bloquearlo tambien
                except Exception:
                    pass
                os._exit(3)
    threading.Thread(target=vigilante, daemon=True, name="watchdog").start()

    try:
        while True:
            latido["t"] = time.time()
            if plc.c is None:
                try:
                    plc.conectar()
                    mq.publish(f"{BASE}/funcional/plc/conexion", "CONECTADO", qos=1, retain=True)
                    print(f"[{ahora()}] Conectado al PLC {a.plc}")
                except Exception as e:
                    mq.publish(f"{BASE}/funcional/plc/conexion", "SIN_CONEXION", qos=1, retain=True)
                    print(f"[{ahora()}] Sin conexion al PLC: {e}. Reintento en 5 s")
                    plc.desconectar()
                    time.sleep(5)
                    continue
            try:
                t0 = time.time()
                with plc.lock:
                    crudos = plc.leer(TAGS)
                for d in TAGS:
                    if d["n"] not in crudos:
                        continue
                    v = crudos[d["n"]]
                    if "valido" in d and not d["valido"](crudos):
                        continue
                    if "conv" in d:
                        v = d["conv"](v)
                    elif d["tipo"] == "real":
                        v = round(v, 6)
                    prev = ultimo.get(d["topic"])
                    banda = 0.05 if d.get("unidad") == "L/min" else 0.0005 if d["tipo"] == "real" else 0
                    if prev is None or abs(v - prev[0]) > banda or t0 - prev[1] >= a.max_silencio:
                        payload = {"value": v, "unit": d.get("unidad"), "timestamp": ahora(),
                                   "source": f"edge-s7200/{d['dir']}", "tag": d["n"]}
                        mq.publish(f"{BASE}/funcional/{d['topic']}", json.dumps(payload), qos=1, retain=True)
                        ultimo[d["topic"]] = (v, t0)
                        print(f"[{payload['timestamp']}] {d['n']:<22}{d['dir']:<7}= {v} {d.get('unidad') or ''}")
                if t0 - ultimo_latido >= 10:
                    mq.publish(f"{BASE}/funcional/edge/heartbeat", ahora(), qos=0, retain=True)
                    # Reafirma el estado: corrige un OFFLINE retenido que haya dejado otra instancia o un Last Will viejo
                    mq.publish(f"{BASE}/funcional/edge/estado", "ONLINE", qos=1, retain=True)
                    mq.publish(f"{BASE}/funcional/plc/conexion", "CONECTADO", qos=1, retain=True)
                    ultimo_latido = t0
            except Exception as e:
                print(f"[{ahora()}] Error de lectura: {e}. Reconectando")
                mq.publish(f"{BASE}/funcional/plc/conexion", "SIN_CONEXION", qos=1, retain=True)
                plc.desconectar()
                time.sleep(2)
                continue
            time.sleep(a.periodo)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        plc.desconectar()
        mq.publish(f"{BASE}/funcional/edge/estado", "OFFLINE", qos=1, retain=True).wait_for_publish(3)
        mq.loop_stop()
        mq.disconnect()


if __name__ == "__main__":
    main()
