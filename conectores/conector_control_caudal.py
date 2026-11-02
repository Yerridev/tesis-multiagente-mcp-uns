#!/usr/bin/env python3
"""Control REAL del MCC-09. No incluye simulador ni escribe salidas Q/AQ directamente."""
import argparse, json, os, socket, time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
import snap7
from snap7.type import Area
from snap7.util import get_bool, get_int, get_real, set_bool, set_int, set_real

BASE = "uss/campus/lab-automatizacion/sl01la07/caudal-mcc09"
CTRL = BASE + "/control"
EQUIPO = "caudal-mcc09"

# Únicas memorias autorizadas, verificadas contra el ladder documentado.
MAPA = {
    "Iniciar": ("M", 0, 2, "bool"),
    "Detener": ("M", 0, 2, "bool"),
    "Setpoint": ("V", 400, None, "real"),
    "AjustarValvula": ("M", 25, None, "int"),
    "kc": ("V", 100, None, "real"),
    "ti": ("V", 108, None, "real"),
    "td": ("V", 116, None, "real"),
}

def iso(): return datetime.now(timezone.utc).isoformat()

class PLC:
    def __init__(self, ip, local_tsap, remote_tsap):
        self.ip, self.lt, self.rt, self.c = ip, local_tsap, remote_tsap, None
    def conectar(self):
        c = snap7.client.Client(); c.set_connection_params(self.ip, self.lt, self.rt); c._connect(self.ip, 0, 0, 102); self.c = c
    def cerrar(self):
        if self.c:
            try: self.c.disconnect()
            except Exception: pass
        self.c = None
    def bloque(self, area, off, size):
        if area == "V": return self.c.db_read(1, off, size)
        if area == "I": return self.c.read_area(Area.PE, 0, off, size)
        return self.c.read_area(Area.MK, 0, off, size)
    def escribir(self, area, off, data):
        if area == "V": self.c.db_write(1, off, data)
        else: self.c.write_area(Area.MK, 0, off, data)
    def bit(self, area, off, bit): return get_bool(self.bloque(area, off, 1), 0, bit)
    def leer(self, spec):
        area, off, bit, tipo = spec; b = self.bloque(area, off, 1 if tipo == "bool" else 2 if tipo == "int" else 4)
        return get_bool(b, 0, bit) if tipo == "bool" else get_int(b, 0) if tipo == "int" else get_real(b, 0)
    def escribir_verificado(self, spec, valor):
        area, off, bit, tipo = spec
        b = self.bloque(area, off, 1 if tipo == "bool" else 2 if tipo == "int" else 4)
        if tipo == "bool": set_bool(b, 0, bit, bool(valor))
        elif tipo == "int": set_int(b, 0, int(valor))
        else: set_real(b, 0, float(valor))
        self.escribir(area, off, b); time.sleep(.25); return self.leer(spec)

class Control:
    def __init__(self, plc, mq, armado): self.plc, self.mq, self.armado = plc, mq, armado
    def ack(self, oid, estado, **extra):
        self.mq.publish(CTRL + "/ack", json.dumps({"id": oid, "estado": estado, "ts": iso(), **extra}), qos=1)
    def validar_fisico(self):
        if not self.armado or os.getenv("CONTROL_CAUDAL_REAL") != "1": return "REAL_NO_ARMADO"
        if not self.plc.bit("M", 0, 3) is False: return "CONTROL_EN_HMI"
        # Entradas reales: I0.0 remoto, I0.1 local.
        remoto = self.plc.bit("I", 0, 0); local = self.plc.bit("I", 0, 1)
        if not remoto or local: return "SELECTOR_NO_REMOTO"
        return None
    def procesar(self, payload):
        try: o = json.loads(payload); oid = str(o["id"]); tipo = str(o["tipo"])
        except Exception: return
        motivo = self.validar_fisico()
        if motivo: self.ack(oid, "Rechazado", motivo=motivo, escrito=False); return
        clave = str(o.get("parametro", "")).lower() if tipo == "ParametroPid" else tipo
        spec = MAPA.get(clave)
        if not spec: self.ack(oid, "Rechazado", motivo="DIRECCION_NO_PERMITIDA", escrito=False); return
        valor = 1 if tipo == "Iniciar" else 0 if tipo == "Detener" else o.get("valor")
        if tipo == "Setpoint" and (not isinstance(valor, (int,float)) or not 0 <= valor <= 140):
            self.ack(oid, "Rechazado", motivo="RANGO_INVALIDO", escrito=False); return
        if tipo == "AjustarValvula":
            if not isinstance(valor, (int,float)) or not 0 <= valor <= 100:
                self.ack(oid, "Rechazado", motivo="RANGO_INVALIDO", escrito=False); return
            valor = round(valor * 320)  # 0..100 % -> 0..32000 cuentas
        # Arranque bloqueado por nivel bajo físico I0.2.
        if tipo == "Iniciar" and self.plc.bit("I", 0, 2):
            self.ack(oid, "Rechazado", motivo="NIVEL_BAJO_T1", escrito=False); return
        self.ack(oid, "Aceptado", escrito=False)
        try:
            if tipo == "AjustarValvula":
                actual = int(self.plc.leer(spec)); destino = int(valor); paso = 320  # máximo 1 % cada 100 ms
                while actual != destino:
                    actual += max(-paso, min(paso, destino - actual)); self.plc.escribir_verificado(spec, actual); time.sleep(.1)
                leido = self.plc.leer(spec); esperado = destino; tolerancia = 1
            else:
                leido = self.plc.escribir_verificado(spec, valor); esperado = valor; tolerancia = .001 if spec[3] == "real" else 0
            self.ack(oid, "Escrito", escrito=True, valor_esperado=esperado)
            if abs(float(leido)-float(esperado)) <= tolerancia:
                self.ack(oid, "Confirmado", escrito=True, valor_esperado=esperado, valor_leido=leido)
            else: self.ack(oid, "Error", motivo="CONFIRMACION_NO_COINCIDE", escrito=True, valor_esperado=esperado, valor_leido=leido)
        except Exception as e: self.ack(oid, "Error", motivo="PLC_ERROR:" + str(e), escrito=False)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--plc",default="192.168.114.7"); p.add_argument("--broker",default="127.0.0.1"); p.add_argument("--local-tsap",default="1000"); p.add_argument("--remote-tsap",default="1000"); p.add_argument("--habilitado-real",action="store_true"); a=p.parse_args()
    socket.setdefaulttimeout(5); plc=PLC(a.plc,int(a.local_tsap,16),int(a.remote_tsap,16)); plc.conectar()
    mq=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id="control-caudal-"+socket.gethostname()); ctl=Control(plc,mq,a.habilitado_real)
    mq.on_message=lambda c,u,m: ctl.procesar(m.payload.decode("utf-8","replace")); mq.connect(a.broker,1883,30); mq.subscribe(CTRL+"/cmd",qos=1)
    mq.publish(CTRL+"/state",json.dumps({"modo":"REAL" if a.habilitado_real and os.getenv("CONTROL_CAUDAL_REAL")=="1" else "BLOQUEADO","plc":"CONECTADO","ts":iso()}),qos=1,retain=True)
    try: mq.loop_forever()
    finally: plc.cerrar()
if __name__ == "__main__": main()
