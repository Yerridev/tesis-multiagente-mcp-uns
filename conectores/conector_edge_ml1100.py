"""
Conector edge SOLO LECTURA: MicroLogix 1100 (modulo de nivel MCN-09/001) -> MQTT (UNS).  v0.2

PLC: MicroLogix 1100 (1763-LEC) + 1762-IF2OF2, IP 192.168.114.9, EtherNet/IP (PCCC) puerto 44818.
Mapa de variables: Y:\\proyects26\\tesis\\nivel\\tags_nivel.yaml (borrador v0.1, 19-oct-2026), obtenido de
la logica ladder del proyecto "upload final.RSS" (Inducontrol) y de la prueba en marcha manual.

Observaciones de la prueba (19-oct-2026, modo manual):
  - N7:4 (PV del PID PD12:0) viene del sensor ultrasonico TS-30S, que mide DISTANCIA:
    el valor BAJA al llenar el tanque y SUBE al vaciarlo (rango visto 11104..16536).
  - O:0/2 y O:0/3 = 1 con la bomba en marcha. O:0/4 abre la valvula Belimo (T4:0, 35 s de carrera).
  - O:1.0 = 0 en manual (el potenciometro manda directo al variador).

Calibracion del nivel (20-oct-2026, tanque 2, 4 puntos 0/15/30/39 cm, error max ~0,5 cm):
    nivel_cm = (16348 - N7:4) / 400
    El sensor satura cerca de 41 cm (N7:4 ~ 0) aunque el tanque 2 mide 60 cm.
    nivel/cm usa mediana de 3 muestras para eliminar picos de eco; nivel/raw se publica sin filtro.
Prueba 20-oct-2026 (modo manual):
    I:1.5 = potenciometro (sigue al mando aun con bomba parada); ~0,00195 Hz/cuenta en el variador (2 puntos).
    I:0/0 = selector REMOTO, I:0/1 = selector LOCAL (solo en LOCAL arranca la bomba).
    I:0/2 = interruptor de nivel bajo del tanque 1 (1 = hay agua); con 0 la bomba se detiene y O:0/1 enciende.
    I:0/4 = pulsador de ARRANQUE.

No contiene ninguna funcion de escritura al PLC (no se usa plc.write).

Instalacion:  pip install pycomm3 paho-mqtt
Uso:          python conector_edge_ml1100.py
"""
import argparse
import json
import socket
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
from pycomm3 import SLCDriver

BASE = "uss/campus/lab-automatizacion/sl01la07/nivel-mcn09"
TZ_LIMA = timezone(timedelta(hours=-5))

# Calibracion del sensor ultrasonico (tanque 2) - ver docstring
CAL_CERO = 16348.0          # N7:4 con 0 cm
CAL_CUENTAS_POR_CM = 400.0  # N7:4 baja 400 cuentas por cada cm que sube el agua
ALTURA_TANQUE2_CM = 60.0
LIMITE_SENSOR_RAW = 300     # por debajo de esto el sensor esta saturado (~40 cm)
HZ_POR_CUENTA_POT = 0.00195 # potenciometro -> frecuencia del variador (estimado, 2 puntos)


def raw_a_cm(x):
    return round((CAL_CERO - x) / CAL_CUENTAS_POR_CM, 1)

# Lecturas por bloque (una peticion por bloque). Las claves son las que usan los TAGS.
BLOQUES = {
    "I0": "I:0.0",
    "O0": "O:0.0",
    "I1_5": "I:1.5",
    "O1_0": "O:1.0",
    "B3": "B3:0{2}",
    "N7": "N7:0{21}",
    "F8": "F8:4{3}",
    "T4_0": "T4:0.ACC",
    "T4_1": "T4:1.ACC",
}


def bit(clave, n):
    return lambda d: bool((d[clave] >> n) & 1)


def palabra(clave, i=None):
    return (lambda d: d[clave]) if i is None else (lambda d: d[clave][i])


# estado: confirmado | hipotesis (se publica en el catalogo para que el agente lo sepa)
TAGS = [
    # --- Proceso ---
    {"n": "NIVEL_RAW", "dir": "N7:4", "f": palabra("N7", 4), "topic": "nivel/raw", "unidad": "cuentas",
     "estado": "confirmado", "desc": "PV del PID PD12:0 (sensor ultrasonico TS-30S, mide distancia: baja al llenar)"},
    {"n": "NIVEL_CM", "dir": "N7:4", "f": palabra("NIVEL_MED"), "conv": raw_a_cm, "topic": "nivel/cm", "unidad": "cm",
     "estado": "confirmado", "desc": "Nivel del tanque 2 calibrado en 4 puntos: (16348 - N7:4)/400, mediana de 3 muestras; valido hasta ~40 cm"},
    {"n": "NIVEL_PCT", "dir": "N7:4", "f": palabra("NIVEL_MED"), "topic": "nivel/pct", "unidad": "%",
     "conv": lambda x: round(100.0 * raw_a_cm(x) / ALTURA_TANQUE2_CM, 1),
     "estado": "confirmado", "desc": "Nivel del tanque 2 en % de su altura total (60 cm)"},
    {"n": "SENSOR_SATURADO", "dir": "N7:4", "f": lambda d: d["NIVEL_MED"] < LIMITE_SENSOR_RAW, "topic": "nivel/fuera_rango_sensor",
     "estado": "confirmado", "desc": "True si el agua supera el rango util del sensor (~40 cm); el valor en cm deja de ser fiable"},
    {"n": "POTENCIOMETRO_RAW", "dir": "I:1.5", "f": palabra("I1_5"), "topic": "bomba/potenciometro_raw", "unidad": "cuentas",
     "estado": "confirmado", "desc": "Potenciometro del tablero (consigna de velocidad en modo LOCAL)"},
    {"n": "FRECUENCIA_ESTIMADA", "dir": "I:1.5", "f": palabra("I1_5"), "topic": "bomba/frecuencia_estimada_hz", "unidad": "Hz",
     "conv": lambda x: round(x * HZ_POR_CUENTA_POT, 1), "estado": "hipotesis",
     "desc": "Frecuencia aproximada del variador ATV11 segun el potenciometro (2 puntos: 24,6 y 33 Hz)"},
    {"n": "SALIDA_VARIADOR_RAW", "dir": "O:1.0", "f": palabra("O1_0"), "topic": "bomba/salida_plc_raw", "unidad": "cuentas",
     "estado": "confirmado", "desc": "Consigna analogica PLC->variador; 0 en modo manual"},
    # --- Estado digital ---
    {"n": "BOMBA_MARCHA", "dir": "O:0/2", "f": bit("O0", 2), "topic": "estado/bomba_marcha",
     "estado": "confirmado", "desc": "Bomba/variador en marcha"},
    {"n": "PILOTO_MARCHA", "dir": "O:0/3", "f": bit("O0", 3), "topic": "estado/piloto_marcha",
     "estado": "confirmado", "desc": "Salida activa junto con la marcha de la bomba"},
    {"n": "VALVULA_ABRIENDO", "dir": "O:0/4", "f": bit("O0", 4), "topic": "valvula/abriendo",
     "estado": "confirmado", "desc": "Valvula Belimo LRB24-3 recibiendo orden de ABRIR"},
    {"n": "VALVULA_CERRANDO", "dir": "O:0/5", "f": bit("O0", 5), "topic": "valvula/cerrando",
     "estado": "hipotesis", "desc": "Valvula Belimo LRB24-3 recibiendo orden de CERRAR"},
    {"n": "T_APERTURA_ACC", "dir": "T4:0.ACC", "f": palabra("T4_0"), "topic": "valvula/t_apertura", "unidad": "s",
     "conv": lambda x: round(x / 100.0, 2), "estado": "confirmado", "desc": "Tiempo acumulado de apertura (base 0.01 s, carrera 35 s)"},
    {"n": "T_CIERRE_ACC", "dir": "T4:1.ACC", "f": palabra("T4_1"), "topic": "valvula/t_cierre", "unidad": "s",
     "conv": lambda x: round(x / 100.0, 2), "estado": "hipotesis", "desc": "Tiempo acumulado de cierre (base 0.01 s)"},
    {"n": "REMOTO", "dir": "I:0/0", "f": bit("I0", 0), "topic": "estado/selector_remoto",
     "estado": "confirmado", "desc": "Selector en REMOTO (control desde PC/SCADA; hoy sin SCADA solo abre la valvula)"},
    {"n": "LOCAL", "dir": "I:0/1", "f": bit("I0", 1), "topic": "estado/selector_local",
     "estado": "confirmado", "desc": "Selector en LOCAL (bomba por potenciometro y pulsador de arranque)"},
    {"n": "TANQUE1_CON_AGUA", "dir": "I:0/2", "f": bit("I0", 2), "topic": "estado/tanque1_con_agua",
     "estado": "confirmado", "desc": "Interruptor de nivel bajo del tanque 1 (reserva): False = nivel bajo, la bomba se detiene"},
    {"n": "NIVEL_BAJO_TANQUE1", "dir": "O:0/1", "f": bit("O0", 1), "topic": "estado/alarma_nivel_bajo_tanque1",
     "estado": "confirmado", "desc": "Piloto de nivel bajo del tanque 1"},
    {"n": "MANDO_I03", "dir": "I:0/3", "f": bit("I0", 3), "topic": "estado/mando_i03",
     "estado": "hipotesis", "desc": "Probable interruptor de NIVEL ALTO del tanque 1 (manual: T1 tiene interruptores bajo y alto)"},
    {"n": "PILOTO_O00", "dir": "O:0/0", "f": bit("O0", 0), "topic": "estado/piloto_o00",
     "estado": "hipotesis", "desc": "Probable piloto ALARMA NIVEL ALTO del tablero (va junto con I:0/3)"},
    {"n": "ARRANQUE", "dir": "I:0/4", "f": bit("I0", 4), "topic": "estado/pulsador_arranque",
     "estado": "confirmado", "desc": "Pulsador de ARRANQUE (pulso corto; puede no verse a 1 s de muestreo)"},
    {"n": "ENTRADA_5", "dir": "I:0/5", "f": bit("I0", 5), "topic": "estado/entrada_5",
     "estado": "hipotesis", "desc": "Siempre 1 en las pruebas (posible paro de emergencia NC)"},
    {"n": "BOMBA_MARCHA_INTERNA", "dir": "B3:0/1", "f": lambda d: bool((d["B3"][0] >> 1) & 1), "topic": "estado/marcha_interna",
     "estado": "hipotesis", "desc": "Bit interno = 1 con la bomba en marcha"},
    # --- Control (estaticos sin SCADA/modo remoto) ---
    {"n": "SETPOINT_A_RAW", "dir": "N7:5", "f": palabra("N7", 5), "topic": "pid/setpoint_a_raw", "unidad": "cuentas",
     "estado": "hipotesis", "desc": "Setpoint copiado a PD12:0.SPS en un modo"},
    {"n": "SETPOINT_B_RAW", "dir": "N7:6", "f": palabra("N7", 6), "topic": "pid/setpoint_b_raw", "unidad": "cuentas",
     "estado": "hipotesis", "desc": "Setpoint copiado a PD12:0.SPS en el otro modo"},
    {"n": "PID_CV_RAW", "dir": "N7:14", "f": palabra("N7", 14), "topic": "pid/cv_raw", "unidad": "cuentas",
     "estado": "hipotesis", "desc": "Salida (CV) del PID PD12:0"},
    {"n": "KC_A", "dir": "N7:8", "f": palabra("N7", 8), "topic": "pid/kc_a", "estado": "hipotesis", "desc": "Kc juego A"},
    {"n": "TI_A", "dir": "N7:9", "f": palabra("N7", 9), "topic": "pid/ti_a", "estado": "hipotesis", "desc": "Ti juego A"},
    {"n": "TD_A", "dir": "N7:10", "f": palabra("N7", 10), "topic": "pid/td_a", "estado": "hipotesis", "desc": "Td juego A"},
    {"n": "KC_B", "dir": "N7:11", "f": palabra("N7", 11), "topic": "pid/kc_b", "estado": "hipotesis", "desc": "Kc juego B"},
    {"n": "TI_B", "dir": "N7:12", "f": palabra("N7", 12), "topic": "pid/ti_b", "estado": "hipotesis", "desc": "Ti juego B"},
    {"n": "TD_B", "dir": "N7:13", "f": palabra("N7", 13), "topic": "pid/td_b", "estado": "hipotesis", "desc": "Td juego B"},
    {"n": "T_APERTURA_SP", "dir": "N7:1", "f": palabra("N7", 1), "topic": "valvula/t_apertura_sp", "unidad": "s",
     "conv": lambda x: round(x / 100.0, 2), "estado": "hipotesis", "desc": "Preset de apertura enviado a T4:0 en remoto"},
    {"n": "T_CIERRE_SP", "dir": "N7:2", "f": palabra("N7", 2), "topic": "valvula/t_cierre_sp", "unidad": "s",
     "conv": lambda x: round(x / 100.0, 2), "estado": "hipotesis", "desc": "Preset de cierre enviado a T4:1 en remoto"},
]


def ahora():
    return datetime.now(TZ_LIMA).isoformat(timespec="milliseconds")   # ms: para medir la latencia PLC → backend


def leer(plc):
    d = {}
    for clave, addr in BLOQUES.items():
        t = plc.read(addr)
        if t.error:
            raise IOError(f"{addr}: {t.error}")
        d[clave] = t.value
    return d


def main():
    p = argparse.ArgumentParser(description="Conector MicroLogix 1100 (nivel) -> MQTT (solo lectura)")
    p.add_argument("--plc", default="192.168.114.9")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--puerto", type=int, default=1883)
    p.add_argument("--periodo", type=float, default=1.0)
    p.add_argument("--max-silencio", type=float, default=60.0, help="Publicar al menos cada N s")
    a = p.parse_args()
    socket.setdefaulttimeout(5)

    tags = list(TAGS)
    historial_nivel = []  # ultimas 3 lecturas de N7:4 para la mediana

    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"edge-ml1100-{socket.gethostname()}")
    mq.will_set(f"{BASE}/funcional/edge/estado", "OFFLINE", qos=1, retain=True)
    mq.connect(a.broker, a.puerto, keepalive=30)
    mq.loop_start()
    mq.publish(f"{BASE}/funcional/edge/estado", "ONLINE", qos=1, retain=True)
    catalogo = [{k: v for k, v in t.items() if k not in ("f", "conv")} for t in tags]
    mq.publish(f"{BASE}/descriptivo/variables", json.dumps(catalogo, ensure_ascii=False), qos=1, retain=True)
    mq.publish(f"{BASE}/descriptivo/equipo", json.dumps({
        "plc": "MicroLogix 1100 (1763-LEC)", "modulo_analogico": "1762-IF2OF2", "ip": a.plc,
        "protocolo": "EtherNet/IP (PCCC)", "sensor_nivel": "Ultrasonico TS-30S (mide distancia)",
        "actuadores": "Variador Altivar 11 + bomba Pentax Ultra 7; valvula Belimo LRB24-3 (flotante)",
        "fuente_mapa": "upload final.RSS (RSLogix 500, Inducontrol) + prueba en marcha 19-oct-2026",
        "calibracion_nivel": {"formula": "cm = (16348 - N7:4) / 400", "fecha": "2026-10-20", "puntos_cm": [0, 15, 30, 39],
                               "error_max_cm": 0.5, "rango_util_cm": [0, 40], "altura_tanque2_cm": ALTURA_TANQUE2_CM},
    }, ensure_ascii=False), qos=1, retain=True)

    plc = None
    ultimo, ultimo_latido = {}, 0.0
    print(f"Publicando en mqtt://{a.broker}:{a.puerto}/{BASE}/... (Ctrl+C para detener)")
    try:
        while True:
            if plc is None:
                try:
                    plc = SLCDriver(a.plc)
                    plc.open()
                    mq.publish(f"{BASE}/funcional/plc/conexion", "CONECTADO", qos=1, retain=True)
                    print(f"[{ahora()}] Conectado al PLC {a.plc}")
                except Exception as e:
                    mq.publish(f"{BASE}/funcional/plc/conexion", "SIN_CONEXION", qos=1, retain=True)
                    print(f"[{ahora()}] Sin conexion al PLC: {e}. Reintento en 5 s")
                    plc = None
                    time.sleep(5)
                    continue
            try:
                t0 = time.time()
                d = leer(plc)
                historial_nivel.append(d["N7"][4])
                del historial_nivel[:-3]
                d["NIVEL_MED"] = sorted(historial_nivel)[len(historial_nivel) // 2]
                for t in tags:
                    v = t["f"](d)
                    if "conv" in t:
                        v = t["conv"](v)
                    prev = ultimo.get(t["topic"])
                    if prev is None or v != prev[0] or t0 - prev[1] >= a.max_silencio:
                        payload = {"value": v, "unit": t.get("unidad"), "timestamp": ahora(),
                                   "source": f"edge-ml1100/{t['dir']}", "tag": t["n"]}
                        mq.publish(f"{BASE}/funcional/{t['topic']}", json.dumps(payload), qos=1, retain=True)
                        ultimo[t["topic"]] = (v, t0)
                        print(f"[{payload['timestamp']}] {t['n']:<22}{t['dir']:<9}= {v} {t.get('unidad') or ''}")
                if t0 - ultimo_latido >= 10:
                    mq.publish(f"{BASE}/funcional/edge/heartbeat", ahora(), qos=0, retain=True)
                    # Reafirma el estado: corrige un OFFLINE retenido que haya dejado otra instancia o un Last Will viejo
                    mq.publish(f"{BASE}/funcional/edge/estado", "ONLINE", qos=1, retain=True)
                    mq.publish(f"{BASE}/funcional/plc/conexion", "CONECTADO", qos=1, retain=True)
                    ultimo_latido = t0
            except Exception as e:
                print(f"[{ahora()}] Error de lectura: {e}. Reconectando")
                mq.publish(f"{BASE}/funcional/plc/conexion", "SIN_CONEXION", qos=1, retain=True)
                try:
                    plc.close()
                except Exception:
                    pass
                plc = None
                time.sleep(2)
                continue
            time.sleep(a.periodo)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        if plc:
            try:
                plc.close()
            except Exception:
                pass
        mq.publish(f"{BASE}/funcional/edge/estado", "OFFLINE", qos=1, retain=True).wait_for_publish(3)
        mq.loop_stop()
        mq.disconnect()


if __name__ == "__main__":
    main()
