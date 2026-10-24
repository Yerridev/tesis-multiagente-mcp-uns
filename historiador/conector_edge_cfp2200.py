"""
Conector edge SOLO LECTURA: cFP-2200 (modulo de presion MCP-09/001) -> MQTT (UNS).  v0.4

Cambios v0.4 (24-oct-2026): la entrada AIO-610 Input 3 (perilla CONTROL MANUAL del tablero) se reconfiguro de
'0 to 0.024 Amps' a voltios, como en la configuracion original de Inducontrol (MOD_PRESION.iak). Ahora
POTENCIOMETRO llega en V: se publica como 'bomba/potenciometro_v' (antes 'bomba/potenciometro_ma', x1000).

Cambios v0.3 (21-oct-2026, tras un cierre 'Python has stopped working' en la VM):
  - La reconexion de una variable caida se limita a una vez cada 15 s (antes: cada segundo, creando un
    objeto ActiveX nuevo sin liberar el anterior -> fuga de objetos COM -> caida del proceso).
  - El objeto viejo se libera explicitamente y todas las conexiones se recrean cada 30 min.
  - faulthandler escribe la traza de un cierre nativo en conector_cfp2200_fallas.log.
  - Usar CONECTOR_CFP2200.bat: reinicia el conector solo si se vuelve a cerrar.

PAC: NI Compact FieldPoint cFP-2200 + DI-301 + DO-403 + AIO-610, IP 192.168.114.8, LabVIEW RT 8.6.
Lectura con NI DataSocket (ActiveX CWDSLib.CWDataSocket, instalado con NI-FieldPoint 6.0.11) en modo
ReadAutoUpdate sobre las variables NI-PSP que publica el cFP. Corre en la VM Windows 7 (Python 3.7 32 bits).
NO depende de la PC del laboratorio ni modifica el cFP.

Validado 21-oct-2026 (probe_ni_vm3):
  psp://192.168.114.8/FP/3AIO/00            -> 0.004003  (A, transmisor en 4 mA con bomba parada)
  psp://192.168.114.8/DATOS_PAC/TRANS_PRESION -> 0.004003 (el programa publica la corriente en A, no psi)
  psp://192.168.114.8/DATOS_PAC/SEL_MANUAL  -> True
  psp://192.168.114.8/pid/Kp_PC             -> 3.0

Recuperacion del equipo (21-oct-2026): DIP switches en mantenimiento, boot line corrupta (reset 'r'),
reinstalacion FieldPoint 6.0.2, restauracion de startup.rtexe y redeploy de DATOS_PAC.lvlib y pid.lvlib.

Escala de presion (prueba manual 21-oct-2026, 18:26-18:34): la HMI TPC-2106T mostro 0.803 y 0.919 psi
cuando el transmisor marcaba ~4.148 y ~4.170 mA -> la escala del programa original es
    psi = (mA - 4) / 16 * 87   (0-6 bar)
Confirmado contra la HMI (no contra manometro: el manometro del modulo esta averiado).
En reposo el transmisor marca 4.02-4.035 mA (~0.1-0.2 psi de offset de cero).
En modo MANUAL el programa copia la perilla CONTROL MANUAL (AIO In3) a AO0 -> AI1 del Altivar; la valvula queda
en 5 V (50 %). Hasta el 24-oct-2026 no funcionaba: In3 estaba configurada en amperios (AO0 recibia ~0,004 V) y
el Altivar 11 (gama Asia ...M3A) estaba en mando local de fabrica. Corregido: Altivar tCC=2C, LSr=tEr, AIt=10U.

No contiene ninguna funcion de escritura: DataSocket se abre solo en modo lectura (2 = ReadAutoUpdate).

Instalacion (VM):  pip install pywin32 paho-mqtt
Uso (VM):          python conector_edge_cfp2200.py --broker <IP de la laptop con Mosquitto>
"""
import argparse
import faulthandler
import json
import math
import os
import socket
import time
from datetime import datetime, timezone, timedelta

_LOG_FALLAS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "conector_cfp2200_fallas.log"), "a")
faulthandler.enable(file=_LOG_FALLAS, all_threads=True)

import pythoncom
import win32com.client
import paho.mqtt.client as mqtt

BASE = "uss/campus/lab-automatizacion/sl01la07/presion-mcp09"
TZ_LIMA = timezone(timedelta(hours=-5))
CFP = "192.168.114.8"
DS_READ_AUTOUPDATE = 2
DS_STATUS_OK = 2           # visto en las pruebas: 2 = conexion activa

PSI_FONDO_ESCALA = 87.02   # 6 bar (hipotesis, pendiente calibracion)


def a_ma(amp):
    return round(amp * 1000.0, 3)


def a_psi(amp):
    return round(max(0.0, (amp * 1000.0 - 4.0) / 16.0 * PSI_FONDO_ESCALA), 2)


def b(x):
    return bool(x)


# url relativa a psp://<cFP>/ ; un mismo url puede alimentar varios topicos (conv distinta)
TAGS = [
    # --- Proceso ---
    {"n": "TRANS_PRESION", "url": "DATOS_PAC/TRANS_PRESION", "conv": a_ma, "topic": "presion/transmisor_ma", "unidad": "mA",
     "estado": "confirmado", "desc": "Corriente del transmisor Danfoss MBS 3000 segun el programa (TRANS_PRESION viene en A)"},
    {"n": "TRANS_PRESION", "url": "DATOS_PAC/TRANS_PRESION", "conv": a_psi, "topic": "presion/psi", "unidad": "psi",
     "estado": "confirmado", "desc": "Presion de T2: (mA-4)/16*87, misma escala que la HMI del programa original (validado 21-oct-2026)"},
    {"n": "AI0", "url": "FP/3AIO/00", "conv": a_ma, "topic": "presion/ai0_ma", "unidad": "mA",
     "estado": "confirmado", "desc": "Canal crudo AIO-610 Input 0 (respaldo independiente del programa)"},
    {"n": "POTENCIOMETRO", "url": "DATOS_PAC/POTENCIOMETRO", "conv": lambda x: round(x, 3), "topic": "bomba/potenciometro_v", "unidad": "V",
     "estado": "confirmado", "desc": "Perilla CONTROL MANUAL del tablero (AIO-610 Input 3, 0-10 V); en LOCAL el programa la copia a la consigna del variador (AO0)"},
    {"n": "VARIADOR", "url": "DATOS_PAC/VARIADOR", "conv": lambda x: round(x, 3), "topic": "bomba/salida_variador", "unidad": "V",
     "estado": "confirmado", "desc": "Consigna 0-10 V al variador Altivar 11 (AIO-610 Output 0); = salida del PID en REMOTO, 0 en LOCAL"},
    {"n": "VAL_PROPOR", "url": "DATOS_PAC/VAL_PROPOR", "conv": lambda x: round(x, 3), "topic": "valvula/salida", "unidad": "V",
     "estado": "confirmado", "desc": "Consigna 0-10 V a la valvula proporcional Danfoss EV260B (AIO-610 Output 1); 1 V = 10 % de apertura"},
    # --- Estado digital ---
    {"n": "SEL_AUTO", "url": "DATOS_PAC/SEL_AUTO", "conv": b, "topic": "estado/selector_remoto", "estado": "confirmado",
     "desc": "Selector CONTROL en REMOTO = mando automatico, PID con supervisor PC/HMI (DI Ch0; prueba 21-oct-2026)"},
    {"n": "SEL_MANUAL", "url": "DATOS_PAC/SEL_MANUAL", "conv": b, "topic": "estado/selector_local", "estado": "confirmado",
     "desc": "Selector CONTROL en LOCAL = mando manual con pulsadores (DI Ch1)"},
    {"n": "ARRANQUE_MANUAL", "url": "DATOS_PAC/ARRANQUE_MANUAL", "conv": b, "topic": "estado/pulsador_arranque",
     "estado": "confirmado", "desc": "Pulsador ARRANQUE (DI Ch2, pulso corto)"},
    {"n": "PARADA_MANUAL", "url": "DATOS_PAC/PARADA_MANUAL", "conv": b, "topic": "estado/pulsador_parada",
     "estado": "hipotesis", "desc": "Pulsador PARADA (DI Ch3; activo en reposo, probablemente NC)"},
    {"n": "PRESOS", "url": "DATOS_PAC/PRESOS", "conv": b, "topic": "estado/presostato", "estado": "hipotesis",
     "desc": "Presostato Danfoss KPI (DI Ch4)"},
    {"n": "SWITCH_NB", "url": "DATOS_PAC/SWITCH_NB", "conv": b, "topic": "estado/switch_nivel_bajo", "estado": "hipotesis",
     "desc": "Interruptor de nivel bajo T1 (DI Ch5)"},
    {"n": "SWITCH_NA", "url": "DATOS_PAC/SWITCH_NA", "conv": b, "topic": "estado/switch_nivel_alto", "estado": "hipotesis",
     "desc": "Interruptor de nivel alto T1 (DI Ch6)"},
    {"n": "LED_SIST_FUN", "url": "DATOS_PAC/LED_SIST_FUN", "conv": b, "topic": "estado/sistema_funcionando",
     "estado": "confirmado", "desc": "Piloto sistema funcionando (DO Ch0)"},
    {"n": "ACT_VARIADOR", "url": "DATOS_PAC/ACT_VARIADOR", "conv": b, "topic": "estado/bomba_habilitada",
     "estado": "confirmado", "desc": "Habilitacion/marcha del variador (DO Ch1)"},
    {"n": "LED_NA", "url": "DATOS_PAC/LED_NA", "conv": b, "topic": "estado/alarma_nivel_alto", "estado": "confirmado",
     "desc": "Piloto nivel alto (DO Ch2)"},
    {"n": "LED_NB", "url": "DATOS_PAC/LED_NB", "conv": b, "topic": "estado/alarma_nivel_bajo", "estado": "confirmado",
     "desc": "Piloto nivel bajo (DO Ch3)"},
    # --- Control PID (los escribe el supervisor PC/HMI; sin supervisor pueden no tener valor) ---
    {"n": "setpoint_pc", "url": "pid/setpoint_pc", "topic": "pid/setpoint_pc", "unidad": "psi", "estado": "confirmado",
     "desc": "Setpoint en psi cuando supervisa el SCADA de la PC (10 y 20 psi en la prueba del 21-oct-2026)"},
    {"n": "SETPOINT_TPM", "url": "pid/SETPOINT_TPM", "topic": "pid/setpoint_hmi", "unidad": "psi", "estado": "hipotesis",
     "desc": "Setpoint cuando supervisa la HMI TPC-2106T"},
    {"n": "salida_pid", "url": "pid/salida_pid", "topic": "pid/cv", "unidad": "V", "estado": "confirmado",
     "desc": "Salida del PID en V (0-10 V hacia el variador); se satura en 10 V"},
    {"n": "valvula_pc", "url": "pid/valvula_pc", "topic": "pid/valvula_pc", "unidad": "V", "estado": "confirmado",
     "desc": "Apertura de valvula fijada desde el SCADA en V (3 = 30 %)"},
    {"n": "Kp_PC", "url": "pid/Kp_PC", "topic": "pid/kp", "estado": "confirmado", "desc": "Ganancia proporcional (PC); 3.0 el 21-oct-2026"},
    {"n": "Ti_PC", "url": "pid/Ti_PC", "topic": "pid/ti", "estado": "hipotesis", "desc": "Tiempo integral (PC)"},
    {"n": "Td_PC", "url": "pid/Td_PC", "topic": "pid/td", "estado": "hipotesis", "desc": "Tiempo derivativo (PC)"},
]


def ahora():
    return datetime.now(TZ_LIMA).isoformat(timespec="seconds")


def bombear(segundos):
    fin = time.time() + segundos
    while time.time() < fin:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.02)


class Lector:
    """Una conexion DataSocket (solo lectura) por cada URL distinto."""

    REINTENTO_S = 15.0          # una variable caida se reabre como maximo cada 15 s
    RECICLAR_S = 30 * 60.0      # todas las conexiones se recrean cada 30 min (evita fugas del ActiveX)

    def __init__(self, cfp, urls):
        self.cfp = cfp
        self.urls = sorted(set(urls))
        self.ds = {}
        self.ultimo_intento = {}
        self.creado = 0.0

    def conectar(self):
        self.cerrar()
        for u in self.urls:
            self._abrir(u)
        self.creado = time.time()
        bombear(3)

    def _soltar(self, u):
        d = self.ds.pop(u, None)
        if d is not None:
            try:
                d.Disconnect()
            except Exception:
                pass
            del d

    def _abrir(self, u):
        self.ultimo_intento[u] = time.time()
        self._soltar(u)
        try:
            d = win32com.client.Dispatch("CWDSLib.CWDataSocket")
            d.ConnectTo("psp://{}/{}".format(self.cfp, u), DS_READ_AUTOUPDATE)
            self.ds[u] = d
        except Exception as e:
            print("[{}] No se pudo abrir {}: {}".format(ahora(), u, e))

    def mantener(self):
        """Reabre variables ausentes (con espera) y recicla todas las conexiones periodicamente."""
        if time.time() - self.creado >= self.RECICLAR_S:
            print("[{}] Reciclando conexiones DataSocket".format(ahora()))
            self.conectar()
            return
        for u in self.urls:
            if u not in self.ds and time.time() - self.ultimo_intento.get(u, 0) >= self.REINTENTO_S:
                self._abrir(u)

    def leer(self):
        out, ok = {}, 0
        for u, d in list(self.ds.items()):
            try:
                st = d.Status
                v = d.Data.Value
            except Exception:
                st, v = None, None
            if st == DS_STATUS_OK and v is not None and not (isinstance(v, float) and math.isnan(v)):
                out[u] = v
                ok += 1
            elif st is not None and st != DS_STATUS_OK and time.time() - self.ultimo_intento.get(u, 0) >= self.REINTENTO_S:
                print("[{}] Reabriendo {} (status={})".format(ahora(), u, st))
                self._abrir(u)   # reintenta esa conexion, como maximo cada REINTENTO_S
        return out, ok

    def cerrar(self):
        for u in list(self.ds):
            self._soltar(u)


def nuevo_cliente_mqtt(cid):
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)   # paho-mqtt 2.x
    except AttributeError:
        return mqtt.Client(client_id=cid)                                      # paho-mqtt 1.x


def main():
    p = argparse.ArgumentParser(description="Conector cFP-2200 (presion) DataSocket -> MQTT (solo lectura)")
    p.add_argument("--cfp", default=CFP)
    p.add_argument("--broker", default="localhost", help="IP del Mosquitto (la laptop host si corre en la VM)")
    p.add_argument("--puerto", type=int, default=1883)
    p.add_argument("--periodo", type=float, default=1.0)
    p.add_argument("--max-silencio", type=float, default=60.0, help="Publicar al menos cada N s")
    a = p.parse_args()

    mq = nuevo_cliente_mqtt("edge-cfp2200-{}".format(socket.gethostname()))
    mq.will_set(BASE + "/funcional/edge/estado", "OFFLINE", qos=1, retain=True)
    mq.connect(a.broker, a.puerto, keepalive=30)
    mq.loop_start()
    mq.publish(BASE + "/funcional/edge/estado", "ONLINE", qos=1, retain=True)
    catalogo = [{**{k: v for k, v in t.items() if k != "conv"}, "dir": t["url"]} for t in TAGS]
    mq.publish(BASE + "/descriptivo/variables", json.dumps(catalogo, ensure_ascii=False), qos=1, retain=True)
    mq.publish(BASE + "/descriptivo/equipo", json.dumps({
        "plc": "NI Compact FieldPoint cFP-2200 (LabVIEW RT 8.6, FieldPoint 6.0.2)",
        "modulos": ["cFP-DI-301 @1", "cFP-DO-403 @2", "cFP-AIO-610 @3"], "ip": a.cfp,
        "protocolo": "NI-PSP leido con NI DataSocket (ActiveX) desde VM Windows 7, solo lectura",
        "transmisor": "Danfoss MBS 3000, 0-6 bar, 4-20 mA",
        "actuadores": "Variador Altivar 11 + bomba Pentax Ultra U5 1.2 HP; valvula proporcional Danfoss EV260B 0-10 V",
        "fuente_mapa": "MOD_PRESION.lvproj, DATOS_PAC.lvlib, pid.lvlib, i_o.xlsx, manual MCP-09/001 (Inducontrol 2008)",
        "calibracion_presion": {"formula": "psi = (mA - 4) / 16 * 87", "fecha": "2026-10-21",
                                "validado_contra": "HMI TPC-2106T (manometro averiado)", "offset_reposo_ma": 0.03},
    }, ensure_ascii=False), qos=1, retain=True)

    lector = Lector(a.cfp, [t["url"] for t in TAGS])
    lector.conectar()
    ultimo, ultimo_latido, conectado = {}, 0.0, None
    print("Leyendo {} y publicando en mqtt://{}:{}/{}/... (Ctrl+C para detener)".format(a.cfp, a.broker, a.puerto, BASE))
    try:
        while True:
            t0 = time.time()
            bombear(a.periodo)                 # procesa los eventos de DataSocket durante el periodo
            datos, ok = lector.leer()
            lector.mantener()
            hay = ok > 0
            if hay != conectado:
                mq.publish(BASE + "/funcional/plc/conexion", "CONECTADO" if hay else "SIN_CONEXION", qos=1, retain=True)
                print("[{}] cFP {}".format(ahora(), "CONECTADO ({} variables)".format(ok) if hay else "SIN DATOS"))
                conectado = hay
            for t in TAGS:
                if t["url"] not in datos:
                    continue
                v = datos[t["url"]]
                v = t["conv"](v) if "conv" in t else round(float(v), 4)
                prev = ultimo.get(t["topic"])
                if prev is None or v != prev[0] or t0 - prev[1] >= a.max_silencio:
                    payload = {"value": v, "unit": t.get("unidad"), "timestamp": ahora(),
                               "source": "edge-cfp2200/" + t["url"], "tag": t["n"]}
                    mq.publish(BASE + "/funcional/" + t["topic"], json.dumps(payload), qos=1, retain=True)
                    ultimo[t["topic"]] = (v, t0)
                    print("[{}] {:<28}= {} {}".format(payload["timestamp"], t["topic"], v, t.get("unidad") or ""))
            if t0 - ultimo_latido >= 10:
                mq.publish(BASE + "/funcional/edge/heartbeat", ahora(), qos=0, retain=True)
                mq.publish(BASE + "/funcional/edge/estado", "ONLINE", qos=1, retain=True)
                ultimo_latido = t0
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        lector.cerrar()
        mq.publish(BASE + "/funcional/edge/estado", "OFFLINE", qos=1, retain=True).wait_for_publish()
        mq.loop_stop()
        mq.disconnect()


if __name__ == "__main__":
    main()
