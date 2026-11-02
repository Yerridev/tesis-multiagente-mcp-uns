#!/usr/bin/env python3
"""Control protegido del MCT-09 (Twido).

Solo permite memorias de mando identificadas en el programa y SCADA antiguo:
  %M30    inicio/parada del lazo de PC
  %MW100  setpoint PID, 0..4095 = 0..100 C
  %MW101..103 parametros PID Kp, Ti y Td.
Nunca escribe %Q ni %MW10 (variador).
Modo real exige: --habilitado-real, CONTROL_TEMPERATURA_REAL=1,
selector PC (%M0) activo, HMI (%M1) inactivo y sin fallas de nivel.
"""
from __future__ import annotations
import argparse, json, os, socket, time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

BASE = "uss/campus/lab-automatizacion/sl01la07/temperatura-mct09"
CTRL = BASE + "/control"
EQUIPO = "temp-mct09"

def iso(): return datetime.now(timezone.utc).isoformat()

def call(fn, *args, unit, **kw):
    for key in ("device_id", "slave", "unit"):
        try: return fn(*args, **kw, **{key: unit})
        except TypeError: pass
    return fn(*args, **kw)

class Twido:
    def __init__(self, host, unit): self.host, self.unit, self.c = host, unit, None
    def connect(self):
        self.close(); self.c = ModbusTcpClient(self.host, port=502, timeout=4)
        if not self.c.connect(): raise ConnectionError("SIN_CONEXION_TCP")
        for u in (self.unit, 255) if self.unit != 255 else (255,):
            r = call(self.c.read_holding_registers, 0, count=1, unit=u)
            if not r.isError(): self.unit = u; return
        self.close(); raise ConnectionError("SIN_RESPUESTA_MODBUS")
    def close(self):
        if self.c:
            try: self.c.close()
            except Exception: pass
        self.c = None
    def req(self, fn, *args, **kw):
        if not self.c: self.connect()
        try:
            r = call(fn, *args, unit=self.unit, **kw)
            if r.isError(): raise IOError(str(r))
            return r
        except Exception:
            self.close(); raise
    def coil(self, address):
        if not self.c: self.connect()
        return bool(self.req(self.c.read_coils, address, count=1).bits[0])
    def reg(self, address):
        if not self.c: self.connect()
        return int(self.req(self.c.read_holding_registers, address, count=1).registers[0])
    def write_coil(self, address, value):
        if not self.c: self.connect()
        self.req(self.c.write_coil, address, bool(value))
    def write_reg(self, address, value):
        if not self.c: self.connect()
        self.req(self.c.write_register, address, int(value))
    def state(self):
        return {"pc": self.coil(0), "hmi": self.coil(1), "falla_principal": self.coil(20),
                "falla_enfriador": self.coil(21), "sistema": self.coil(12), "bomba": self.coil(13),
                "inicio_pc": self.coil(30), "lazo_pc": self.coil(31)}

def ack(mq, payload, estado, motivo=None, **extra):
    data = {"id": payload.get("id"), "estado": estado, "motivo": motivo, "timestamp": iso(), **extra}
    mq.publish(CTRL + "/ack", json.dumps(data), qos=1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plc", default="192.168.114.10"); ap.add_argument("--unit", type=int, default=1)
    ap.add_argument("--broker", default="127.0.0.1"); ap.add_argument("--puerto", type=int, default=1883)
    ap.add_argument("--habilitado-real", action="store_true")
    a = ap.parse_args(); socket.setdefaulttimeout(5)
    real = a.habilitado_real and os.getenv("CONTROL_TEMPERATURA_REAL") == "1"
    plc = Twido(a.plc, a.unit)
    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="control-temperatura-mct09")

    def on_connect(client, userdata, flags, reason_code, properties=None):
        client.subscribe(CTRL + "/cmd", qos=1)
        client.publish(CTRL + "/state", json.dumps({"modo": "REAL" if real else "BLOQUEADO", "escritura": real}), retain=True)

    def on_message(client, userdata, msg):
        try:
            p = json.loads(msg.payload.decode("utf-8")); tipo = p.get("tipo")
            if p.get("equipo") != EQUIPO or tipo not in ("Iniciar", "Detener", "Setpoint", "ParametroPid"):
                return ack(client, p, "Rechazado", "TIPO_DESCONOCIDO", escrito=False)
            if not real: return ack(client, p, "Rechazado", "REAL_NO_ARMADO", escrito=False)
            try: s = plc.state()
            except Exception as ex: return ack(client, p, "Error", "PLC_ERROR:" + str(ex), escrito=False)
            if not s["pc"] or s["hmi"]: return ack(client, p, "Rechazado", "SELECTOR_NO_PC", escrito=False)
            if tipo == "Iniciar" and (s["falla_principal"] or s["falla_enfriador"]):
                return ack(client, p, "Rechazado", "FALLA_NIVEL", escrito=False)
            ack(client, p, "Aceptado", escrito=False)
            if tipo == "Setpoint":
                valor = p.get("valor")
                if not isinstance(valor, (int, float)) or not 15 <= valor <= 50: return ack(client, p, "Rechazado", "RANGO_INVALIDO", escrito=False)
                raw = round(float(valor) * 4095 / 100)
                plc.write_reg(100, raw); time.sleep(.3); leido = plc.reg(100)
                c = round(leido * 100 / 4095, 2)
                if abs(leido - raw) <= 1: return ack(client, p, "Confirmado", escrito=True, valor_esperado=valor, valor_leido=c)
                return ack(client, p, "Error", "LECTURA_NO_COINCIDE", escrito=True, valor_esperado=valor, valor_leido=c)
            if tipo == "ParametroPid":
                direccion = {"kp": 101, "ti": 102, "td": 103}.get(str(p.get("parametro", "")).lower())
                valor = p.get("valor")
                if direccion is None or isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 0 <= valor <= 10000 or valor != int(valor):
                    return ack(client, p, "Rechazado", "PARAMETRO_PID_INVALIDO", escrito=False)
                plc.write_reg(direccion, int(valor)); time.sleep(.3); leido = plc.reg(direccion)
                if leido == int(valor): return ack(client, p, "Confirmado", escrito=True, valor_esperado=valor, valor_leido=leido)
                return ack(client, p, "Error", "LECTURA_NO_COINCIDE", escrito=True, valor_esperado=valor, valor_leido=leido)
            valor = tipo == "Iniciar"; plc.write_coil(30, valor); time.sleep(.3)
            escrito = plc.coil(30)
            if escrito != valor: return ack(client, p, "Error", "LECTURA_NO_COINCIDE", escrito=True, valor_esperado=1 if valor else 0, valor_leido=1 if escrito else 0)
            limite = time.time() + 7
            while time.time() < limite:
                st = plc.state()
                confirmado = st["lazo_pc"] or st["sistema"] if valor else not st["lazo_pc"]
                if confirmado: return ack(client, p, "Confirmado", escrito=True, valor_esperado=1 if valor else 0, valor_leido=1 if escrito else 0)
                time.sleep(.4)
            ack(client, p, "Error", "CONFIRMACION_NO_COINCIDE", escrito=True, valor_esperado=1 if valor else 0, valor_leido=1 if escrito else 0)
        except Exception as ex: ack(client, p if 'p' in locals() else {}, "Error", "ERROR:" + str(ex), escrito=False)

    mq.on_connect, mq.on_message = on_connect, on_message
    mq.connect(a.broker, a.puerto, keepalive=30); mq.loop_forever()

if __name__ == "__main__": main()
