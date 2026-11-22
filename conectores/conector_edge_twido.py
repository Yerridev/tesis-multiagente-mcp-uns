"""
Conector edge SOLO LECTURA: PLC Twido (modulo de temperatura MCT-09/001) -> MQTT (UNS).  v0.1

PLC: Schneider Twido TWDLCAE40DRF + 2x TWDAMM3HT, IP 192.168.114.10, Modbus TCP 502 (unit id 1).
Mapa de variables: Y:\\proyects26\\tesis\\temperatura\\tags_temperatura.yaml (v0.1, 23-oct-2026), obtenido de
Twido1.xtwd (programa de respaldo 2009), del diagrama de scada_mct_04.vi (SCADA original LabVIEW),
de los planos/manual de Inducontrol y de las lecturas en vivo del 23-oct-2026.

Direccionamiento Modbus del Twido: %MWi = holding register i, %Mi = coil i (base 0).
  - FC03 %MW0..23   : temperaturas (copias de %IW0.2.0/1), consigna del variador (%MW10)
  - FC03 %MW100..110: SP, Kp, Ti, Td del PID 0 y su salida numerica (%MW110)
  - FC01 %M0..47    : selector, niveles, pilotos, fallas, inicios (el Twido rechaza 64 coils por peticion)

Escalas (las del SCADA original):
    temperatura_C = raw * 100 / 4095          (4-20 mA -> 0..4095 -> 0..100 C)
    setpoint_C    = %MW100 * 100 / 4095        (el SP va en las MISMAS cuentas que la temperatura)
    variador_%    = %MW10 / 40.96
    salida_PID_%  = %MW110 / 100               (0..10000)
La senal de temperatura tiene ruido de +-1 C con la bomba en marcha: los topics en C usan media movil de 10 muestras;
los topics *_raw se publican sin filtro.

El Twido atiende pocas conexiones Modbus simultaneas (ya hay una permanente del OPC Server de la PC .100):
este conector mantiene UNA sola conexion y la reutiliza.

No contiene ninguna funcion de escritura al PLC (no se usa write_coil / write_register / write_registers).

Instalacion:  pip install pymodbus paho-mqtt
Uso:          python conector_edge_twido.py [--plc 192.168.114.10] [--broker localhost]
"""
import argparse
import json
import socket
import time
from collections import deque
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

BASE = "uss/campus/lab-automatizacion/sl01la07/temperatura-mct09"
TZ_LIMA = timezone(timedelta(hours=-5))

ESCALA_C = 100.0 / 4095.0      # cuentas -> C (temperatura y setpoint)
VARIADOR_POR_PCT = 40.96       # cuentas por % de la consigna del variador
VENTANA_MEDIA = 10             # muestras de la media movil de las temperaturas


def a_c(x):
    return round(x * ESCALA_C, 2)


def mw(i):
    return lambda d: d["MW"][i]


def m(i):
    return lambda d: bool(d["M"][i])


# estado: confirmado | hipotesis (se publica en el catalogo para que el agente lo sepa)
TAGS = [
    # --- Proceso ---
    {"n": "T_PRINCIPAL_RAW", "dir": "%MW0", "f": mw(0), "topic": "temperatura/principal_raw", "unidad": "cuentas",
     "estado": "confirmado", "desc": "Temperatura del tanque principal T2 (con resistencia), copia de %IW0.2.0, PV del PID; sin filtro"},
    {"n": "T_PRINCIPAL_C", "dir": "%MW0", "f": lambda d: d["MEDIA0"], "conv": a_c, "topic": "temperatura/principal_c", "unidad": "C",
     "estado": "confirmado", "desc": "Temperatura del tanque principal: raw*100/4095, media movil de 10 s (escala del SCADA; falta contraste con termometro)"},
    {"n": "T_ENFRIADOR_RAW", "dir": "%MW1", "f": mw(1), "topic": "temperatura/enfriador_raw", "unidad": "cuentas",
     "estado": "confirmado", "desc": "Temperatura del tanque de enfriamiento T1, copia de %IW0.2.1; sin filtro"},
    {"n": "T_ENFRIADOR_C", "dir": "%MW1", "f": lambda d: d["MEDIA1"], "conv": a_c, "topic": "temperatura/enfriador_c", "unidad": "C",
     "estado": "confirmado", "desc": "Temperatura del tanque de enfriamiento: raw*100/4095, media movil de 10 s"},
    {"n": "VARIADOR_RAW", "dir": "%MW10", "f": mw(10), "topic": "bomba/consigna_raw", "unidad": "cuentas",
     "estado": "confirmado", "desc": "Consigna PLC -> variador ATV11 (copiada a %QW0.2.0, 0..4095 = 0..10 V)"},
    {"n": "VARIADOR_PCT", "dir": "%MW10", "f": mw(10), "conv": lambda x: round(x / VARIADOR_POR_PCT, 1),
     "topic": "bomba/consigna_pct", "unidad": "%", "estado": "confirmado",
     "desc": "Velocidad pedida a la bomba en % (100 % = 10 V = 50 Hz con AIt=10U)"},
    # --- Lazo PID 0 ---
    {"n": "SP_RAW", "dir": "%MW100", "f": mw(100), "topic": "pid/setpoint_raw", "unidad": "cuentas",
     "estado": "confirmado", "desc": "Setpoint del PID en cuentas de temperatura; lo escribe el SCADA/HMI y se pierde al apagar el PLC"},
    {"n": "SP_C", "dir": "%MW100", "f": mw(100), "conv": a_c, "topic": "pid/setpoint_c", "unidad": "C",
     "estado": "confirmado", "desc": "Setpoint del PID en C (rango de operacion del fabricante 15-50 C)"},
    {"n": "KP", "dir": "%MW101", "f": mw(101), "topic": "pid/kp", "estado": "confirmado",
     "desc": "Ganancia proporcional (valor de fabrica 5000, unidades internas del Twido)"},
    {"n": "TI", "dir": "%MW102", "f": mw(102), "topic": "pid/ti", "estado": "confirmado",
     "desc": "Tiempo integral (fabrica 10; probablemente decimas de segundo)"},
    {"n": "TD", "dir": "%MW103", "f": mw(103), "topic": "pid/td", "estado": "confirmado",
     "desc": "Tiempo derivativo (fabrica 10; probablemente decimas de segundo)"},
    {"n": "SALIDA_PID_PCT", "dir": "%MW110", "f": mw(110), "conv": lambda x: round(x / 100.0, 1),
     "topic": "pid/salida_pct", "unidad": "%", "estado": "confirmado",
     "desc": "Ciclo de trabajo del PWM de la resistencia calculado por el PID (0..10000 -> 0..100 %)"},
    # --- Entradas digitales ---
    {"n": "SEL_PC", "dir": "%M0", "f": m(0), "topic": "estado/selector_remoto", "estado": "confirmado",
     "desc": "Selector CONTROLADOR en PC (control desde el SCADA de la PC)"},
    {"n": "SEL_HMI", "dir": "%M1", "f": m(1), "topic": "estado/selector_local", "estado": "confirmado",
     "desc": "Selector CONTROLADOR en HMI (control desde la pantalla del tablero); posicion 0 = ambos en False"},
    {"n": "PULS_HAB_ENF", "dir": "%M2", "f": m(2), "topic": "enfriador/pulsador_habilitar", "estado": "confirmado",
     "desc": "Pulsador HABILITAR ENFRIADOR (pulso; puede no verse a 1 s)"},
    {"n": "PULS_DESHAB_ENF", "dir": "%M3", "f": m(3), "topic": "enfriador/pulsador_deshabilitar", "estado": "confirmado",
     "desc": "Pulsador DESHABILITAR ENFRIADOR, contacto NC: True en reposo"},
    {"n": "NIVEL_ALTO_PRINCIPAL", "dir": "%M4", "f": m(4), "topic": "nivel/principal_alto", "estado": "confirmado",
     "desc": "Interruptor de nivel ALTO del tanque principal activado (True bloquea el lazo)"},
    {"n": "NIVEL_BAJO_PRINCIPAL_OK", "dir": "%M5", "f": m(5), "topic": "nivel/principal_bajo_ok", "estado": "confirmado",
     "desc": "Hay agua sobre el interruptor de nivel BAJO del tanque principal (False bloquea el lazo)"},
    {"n": "NIVEL_ALTO_ENFRIADOR", "dir": "%M6", "f": m(6), "topic": "nivel/enfriador_alto", "estado": "confirmado",
     "desc": "Interruptor de nivel ALTO del tanque de enfriamiento activado"},
    {"n": "NIVEL_BAJO_ENFRIADOR_OK", "dir": "%M7", "f": m(7), "topic": "nivel/enfriador_bajo_ok", "estado": "confirmado",
     "desc": "Hay agua sobre el interruptor de nivel BAJO del tanque de enfriamiento"},
    # --- Salidas / estado ---
    {"n": "SISTEMA_FUNCIONANDO", "dir": "%M12", "f": m(12), "topic": "estado/sistema_funcionando", "estado": "confirmado",
     "desc": "Lazo de control en marcha (piloto SISTEMA FUNCIONANDO, Q0.0.2)"},
    {"n": "BOMBA_MARCHA", "dir": "%M13", "f": m(13), "topic": "estado/bomba_marcha", "estado": "confirmado",
     "desc": "Orden de marcha al variador (Q0.0.3 -> LI1 del ATV11)"},
    {"n": "RESISTENCIA_ON", "dir": "%M14", "f": m(14), "topic": "estado/resistencia_on", "estado": "confirmado",
     "desc": "Orden PWM a la resistencia (copia de Q0.0.1). Es la ORDEN del PLC: no prueba que circule corriente"},
    {"n": "ALARMA_ALTO_PRINCIPAL", "dir": "%M15", "f": m(15), "topic": "alarma/nivel_alto_principal", "estado": "confirmado",
     "desc": "Piloto ALARMA NIVEL ALTO del tanque principal"},
    {"n": "ALARMA_BAJO_PRINCIPAL", "dir": "%M16", "f": m(16), "topic": "alarma/nivel_bajo_principal", "estado": "confirmado",
     "desc": "Piloto ALARMA NIVEL BAJO del tanque principal"},
    {"n": "ALARMA_ALTO_ENFRIADOR", "dir": "%M17", "f": m(17), "topic": "alarma/nivel_alto_enfriador", "estado": "confirmado",
     "desc": "Piloto ALARMA NIVEL ALTO del tanque de enfriamiento"},
    {"n": "ALARMA_BAJO_ENFRIADOR", "dir": "%M18", "f": m(18), "topic": "alarma/nivel_bajo_enfriador", "estado": "confirmado",
     "desc": "Piloto ALARMA NIVEL BAJO del tanque de enfriamiento"},
    {"n": "ENFRIADOR_ON", "dir": "%M19", "f": m(19), "topic": "estado/enfriador_on", "estado": "confirmado",
     "desc": "Orden al rele del enfriador (Q0.0.10): enfriador habilitado y temperatura > SP durante %TM0"},
    {"n": "FALLA_NIVEL_PRINCIPAL", "dir": "%M20", "f": m(20), "topic": "falla/nivel_principal", "estado": "confirmado",
     "desc": "Falla de nivel en el tanque principal: detiene el lazo y borra las ordenes de inicio"},
    {"n": "FALLA_NIVEL_ENFRIADOR", "dir": "%M21", "f": m(21), "topic": "falla/nivel_enfriador", "estado": "confirmado",
     "desc": "Falla de nivel en el tanque de enfriamiento: detiene el lazo"},
    # --- Mando ---
    {"n": "INICIO_PC", "dir": "%M30", "f": m(30), "topic": "mando/inicio_remoto", "estado": "confirmado",
     "desc": "Orden de inicio desde el SCADA de la PC (se mantiene en True mientras el lazo corre)"},
    {"n": "LAZO_PC", "dir": "%M31", "f": m(31), "topic": "mando/lazo_remoto", "estado": "confirmado",
     "desc": "Lazo en marcha en modo PC"},
    {"n": "INICIO_HMI", "dir": "%M32", "f": m(32), "topic": "mando/inicio_local", "estado": "confirmado",
     "desc": "Orden de inicio desde la HMI del tablero (via SCADA de la PC)"},
    {"n": "LAZO_HMI", "dir": "%M33", "f": m(33), "topic": "mando/lazo_local", "estado": "confirmado",
     "desc": "Lazo en marcha en modo HMI"},
    {"n": "ENF_HABILITADO_HMI", "dir": "%M40", "f": m(40), "topic": "enfriador/habilitado_local", "estado": "hipotesis",
     "desc": "Enfriador habilitado por los pulsadores del tablero (modo HMI)"},
    {"n": "ENF_HABILITA_PC", "dir": "%M41", "f": m(41), "topic": "enfriador/habilita_pc", "estado": "hipotesis",
     "desc": "Habilitacion del enfriador desde el SCADA (no esta en el respaldo del programa de 2009)"},
    {"n": "ENF_DESHABILITA_PC", "dir": "%M42", "f": m(42), "topic": "enfriador/deshabilita_pc", "estado": "hipotesis",
     "desc": "Deshabilitacion del enfriador desde el SCADA (no esta en el respaldo del programa de 2009)"},
    {"n": "ENF_PERMISO_PC", "dir": "%M43", "f": m(43), "topic": "enfriador/permiso_remoto", "estado": "hipotesis",
     "desc": "Permiso del enfriador en modo PC (selector PC y sin fallas de nivel)"},
    {"n": "T_MAYOR_SP", "dir": "%M44", "f": m(44), "topic": "enfriador/t_mayor_sp", "estado": "confirmado",
     "desc": "Temperatura principal mayor que el SP durante el temporizador %TM0 (condicion para enfriar)"},
]


def ahora():
    return datetime.now(TZ_LIMA).isoformat(timespec="milliseconds")   # ms: para medir la latencia PLC → backend


def _call(fn, *args, unit, **kw):
    """Compatibilidad con pymodbus 3.x (device_id / slave / unit segun la version)."""
    for key in ("device_id", "slave", "unit"):
        try:
            return fn(*args, **kw, **{key: unit})
        except TypeError:
            continue
    return fn(*args, **kw)


def leer(cli, unit):
    r1 = _call(cli.read_holding_registers, 0, count=24, unit=unit)
    r2 = _call(cli.read_holding_registers, 100, count=11, unit=unit)
    r3 = _call(cli.read_coils, 0, count=48, unit=unit)
    for r, q in ((r1, "%MW0..23"), (r2, "%MW100..110"), (r3, "%M0..47")):
        if r.isError():
            raise IOError(f"{q}: {r}")
    regs = {i: v for i, v in enumerate(r1.registers)}
    regs.update({100 + i: v for i, v in enumerate(r2.registers)})
    return {"MW": regs, "M": list(r3.bits[:48])}


def conectar(ip, unit_pref):
    cli = ModbusTcpClient(ip, port=502, timeout=3)
    if not cli.connect():
        raise ConnectionError(f"sin respuesta TCP en {ip}:502")
    for u in (unit_pref, 255) if unit_pref != 255 else (255,):
        r = _call(cli.read_holding_registers, 0, count=1, unit=u)
        if not r.isError():
            return cli, u
    cli.close()
    raise ConnectionError("el PLC acepta TCP pero no responde Modbus (unit 1 ni 255)")


def main():
    p = argparse.ArgumentParser(description="Conector Twido (temperatura) -> MQTT (solo lectura)")
    p.add_argument("--plc", default="192.168.114.10")
    p.add_argument("--unit", type=int, default=1)
    p.add_argument("--broker", default="localhost")
    p.add_argument("--puerto", type=int, default=1883)
    p.add_argument("--periodo", type=float, default=1.0)
    p.add_argument("--max-silencio", type=float, default=60.0, help="Publicar al menos cada N s")
    a = p.parse_args()
    socket.setdefaulttimeout(5)

    hist0, hist1 = deque(maxlen=VENTANA_MEDIA), deque(maxlen=VENTANA_MEDIA)

    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"edge-twido-{socket.gethostname()}")
    mq.will_set(f"{BASE}/funcional/edge/estado", "OFFLINE", qos=1, retain=True)
    mq.connect(a.broker, a.puerto, keepalive=30)
    mq.loop_start()
    mq.publish(f"{BASE}/funcional/edge/estado", "ONLINE", qos=1, retain=True)
    catalogo = [{k: v for k, v in t.items() if k not in ("f", "conv")} for t in TAGS]
    mq.publish(f"{BASE}/descriptivo/variables", json.dumps(catalogo, ensure_ascii=False), qos=1, retain=True)
    mq.publish(f"{BASE}/descriptivo/equipo", json.dumps({
        "plc": "Schneider Twido TWDLCAE40DRF", "modulos_analogicos": "2x TWDAMM3HT (2 entradas + 1 salida, 12 bits)",
        "ip": a.plc, "protocolo": "Modbus TCP 502 (unit id 1)",
        "sensores": "2x Danfoss MBT 5252 Pt100 + transmisor 4-20 mA (principal e enfriador)",
        "actuadores": "Resistencia calefactora por PWM (rele estado solido FOTEK SSR-25DA-H); bomba Pentax Ultra U5 120/3T "
                      "+ variador Altivar 11 ATV11HU29M3A; enfriador (rele R_02)",
        "rango_operacion_c": [15, 50],
        "escalas": {"temperatura_c": "raw*100/4095", "setpoint_c": "%MW100*100/4095", "variador_pct": "%MW10/40.96",
                    "salida_pid_pct": "%MW110/100", "filtro": f"media movil de {VENTANA_MEDIA} muestras en *_c"},
        "fuente_mapa": "Twido1.xtwd (2009) + scada_mct_04.vi (SCADA LabVIEW) + planos/manual Inducontrol + lecturas 23-oct-2026",
        "hmi_scada": "HMI TPC .101 -> variables compartidas en PC .100 -> MOD_TEMP.exe -> OPC Lookout (objeto 'temp') -> PLC",
    }, ensure_ascii=False), qos=1, retain=True)

    cli, unit = None, a.unit
    ultimo, ultimo_latido = {}, 0.0
    print(f"Publicando en mqtt://{a.broker}:{a.puerto}/{BASE}/... (Ctrl+C para detener)")
    try:
        while True:
            if cli is None:
                try:
                    cli, unit = conectar(a.plc, a.unit)
                    mq.publish(f"{BASE}/funcional/plc/conexion", "CONECTADO", qos=1, retain=True)
                    print(f"[{ahora()}] Conectado al PLC {a.plc} (unit id {unit})")
                except Exception as e:
                    mq.publish(f"{BASE}/funcional/plc/conexion", "SIN_CONEXION", qos=1, retain=True)
                    print(f"[{ahora()}] Sin conexion al PLC: {e}. Reintento en 5 s")
                    cli = None
                    time.sleep(5)
                    continue
            try:
                t0 = time.time()
                d = leer(cli, unit)
                hist0.append(d["MW"][0])
                hist1.append(d["MW"][1])
                d["MEDIA0"] = sum(hist0) / len(hist0)
                d["MEDIA1"] = sum(hist1) / len(hist1)
                for t in TAGS:
                    v = t["f"](d)
                    if "conv" in t:
                        v = t["conv"](v)
                    prev = ultimo.get(t["topic"])
                    if prev is None or v != prev[0] or t0 - prev[1] >= a.max_silencio:
                        payload = {"value": v, "unit": t.get("unidad"), "timestamp": ahora(),
                                   "source": f"edge-twido/{t['dir']}", "tag": t["n"]}
                        mq.publish(f"{BASE}/funcional/{t['topic']}", json.dumps(payload), qos=1, retain=True)
                        ultimo[t["topic"]] = (v, t0)
                        print(f"[{payload['timestamp']}] {t['n']:<24}{t['dir']:<8}= {v} {t.get('unidad') or ''}")
                if t0 - ultimo_latido >= 10:
                    mq.publish(f"{BASE}/funcional/edge/heartbeat", ahora(), qos=0, retain=True)
                    # Reafirma el estado: corrige un OFFLINE retenido de otra instancia o de un Last Will viejo
                    mq.publish(f"{BASE}/funcional/edge/estado", "ONLINE", qos=1, retain=True)
                    mq.publish(f"{BASE}/funcional/plc/conexion", "CONECTADO", qos=1, retain=True)
                    ultimo_latido = t0
            except Exception as e:
                print(f"[{ahora()}] Error de lectura: {e}. Reconectando")
                mq.publish(f"{BASE}/funcional/plc/conexion", "SIN_CONEXION", qos=1, retain=True)
                try:
                    cli.close()
                except Exception:
                    pass
                cli = None
                time.sleep(2)
                continue
            time.sleep(a.periodo)
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        if cli:
            try:
                cli.close()
            except Exception:
                pass
        mq.publish(f"{BASE}/funcional/edge/estado", "OFFLINE", qos=1, retain=True).wait_for_publish(3)
        mq.loop_stop()
        mq.disconnect()


if __name__ == "__main__":
    main()
