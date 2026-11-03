#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Control REAL del modulo de presion MCP-09 (NI cFP-2200) desde la VM Windows 7.

Escribe en las VARIABLES DE RED DEL CONTROLADOR (NI-PSP / DataSocket) las mismas
memorias que escribia el SCADA original de 2008 (verificadas en MOD_PRESION/PC.vi):
    DATOS_PAC/INICIO_PC , DATOS_PAC/SALIR_PC , pid/setpoint_pc , pid/Kp_PC , pid/Ti_PC , pid/Td_PC

El PID NO corre aqui: corre en el cFP-2200. Este conector solo manda consigna,
ganancias y la toma/cesion de mando del supervisor.

Gate triple (identico al del modulo de caudal):
    1) --habilitado-real
    2) env CONTROL_PRESION_REAL=1
    3) fisico: selector de control en AUTOMATICO (DI Ch0 = SEL_AUTO) y telemetria fresca

Uso (en la VM LAB-AUTOMATIZACION):
    python conector_control_presion.py --broker 192.168.114.100 --puerto 1884 --habilitado-real
"""
import argparse
import json
import os
import socket
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt
import pythoncom
import win32com.client

BASE = "uss/campus/lab-automatizacion/sl01la07/presion-mcp09"
CTRL = BASE + "/control"
TZ_LIMA = timezone(timedelta(hours=-5))

# DataSocket (INIDSCtl): AccessMode 2 = lectura auto-update, 4 = escritura (verificado
# en la VM contra el cFP-2200: 0 y 1 no existen en el enumerado; 8 es solo lectura).
DS_READ = 2
DS_WRITE = 4
DS_STATUS_OK = 2

# Allowlist: unica variable que cada orden puede tocar.
# IMPORTANTE (verificado 30-oct-2026 sobre el cFP-2200 en servicio):
#   - DATOS_PAC/INICIO_PC y DATOS_PAC/SALIR_PC SI aceptan escritura desde un cliente
#     externo: son las entradas del supervisor del programa RT (tomar/ceder el mando).
#     Escribir INICIO_PC=True arranca la bomba; SALIR_PC=True la detiene.
#   - pid/setpoint_pc es la consigna del supervisor PC documentada en el proyecto
#     original. Solo se acepta con selector AUTOMATICO y PC_TPM activo, y se valida
#     leyendo nuevamente la variable después de escribirla.
#
# Secuencia: el RTApp queda en "cedido el mando" tras un SALIR_PC, asi que para
# arrancar hay que limpiar primero SALIR_PC=False y luego dar INICIO_PC=True
# (flanco de subida). Al detener: INICIO_PC=False (soltar) y SALIR_PC=True.
MAPA = {
    "Iniciar": [("DATOS_PAC/SALIR_PC", False), ("DATOS_PAC/INICIO_PC", True)],
    "Detener": [("DATOS_PAC/INICIO_PC", False), ("DATOS_PAC/SALIR_PC", True)],
}
RANGOS = {"Setpoint": (0.0, 40.0), "kp": (0.0, 20.0), "kc": (0.0, 20.0),
          "ti": (0.0, 60.0), "td": (0.0, 10.0)}
PID_URL = {"kp": "pid/Kp_PC", "kc": "pid/Kp_PC", "ti": "pid/Ti_PC", "td": "pid/Td_PC"}


def ahora():
    return datetime.now(TZ_LIMA).isoformat(timespec="seconds")


def bombear(segundos=0.2):
    fin = time.time() + segundos
    while time.time() < fin:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.02)


class DataSocket:
    """Conexiones DataSocket de lectura y escritura al cFP-2200.

    La conexion se establece de forma asincrona: hay que bombear mensajes COM
    hasta que Status == 2 (OK) antes de leer o escribir.
    """

    def __init__(self, cfp):
        self.cfp = cfp
        self.lectura = {}      # url -> conexion lectura
        self.escritura = {}    # url -> conexion escritura

    def _abrir(self, url, modo):
        d = win32com.client.Dispatch("CWDSLib.CWDataSocket")
        d.ConnectTo("psp://{}/{}".format(self.cfp, url), modo)
        fin = time.time() + 10
        while time.time() < fin:
            bombear(0.3)
            try:
                if d.Status == DS_STATUS_OK:
                    return d
            except Exception:
                pass
        return d

    def abrir_lectura(self, url):
        if url not in self.lectura:
            self.lectura[url] = self._abrir(url, DS_READ)
        return self.lectura[url]

    def abrir_escritura(self, url):
        if url not in self.escritura:
            self.escritura[url] = self._abrir(url, DS_WRITE)
        return self.escritura[url]

    def leer(self, url):
        try:
            d = self.abrir_lectura(url)
            bombear(0.5)
            if d.Status != DS_STATUS_OK:
                return None
            return d.Data.Value
        except Exception:
            return None

    def escribir(self, url, valor):
        d = self.abrir_escritura(url)
        if d.Status != DS_STATUS_OK:
            raise RuntimeError("conexion de escritura no lista (status={})".format(d.Status))
        d.Data.Value = valor
        bombear(0.5)
        try:
            d.Update()
        except Exception:
            pass
        bombear(0.4)
        return True

    def cerrar(self):
        for grupo in (self.lectura, self.escritura):
            for d in list(grupo.values()):
                try:
                    d.Disconnect()
                except Exception:
                    pass
            grupo.clear()


class Control:
    def __init__(self, ds, mq, armado, cfp):
        self.ds = ds
        self.mq = mq
        self.armado = armado
        self.cfp = cfp
        self.ultima_lectura = 0.0

    def ack(self, oid, estado, **extra):
        self.mq.publish(CTRL + "/ack", json.dumps({"id": oid, "estado": estado, "ts": ahora(), **extra}), qos=1)

    def gate(self, ds):
        """Devuelve el motivo del rechazo o None si se puede escribir."""
        if not self.armado or os.getenv("CONTROL_PRESION_REAL") != "1":
            return "REAL_NO_ARMADO"
        if (time.time() - self.ultima_lectura) > 20:
            return "TELEMETRIA_VENCIDA"
        auto = ds.leer("DATOS_PAC/SEL_AUTO")
        if auto is not True:
            return "SELECTOR_NO_AUTOMATICO"
        return None

    def procesar(self, payload):
        # El callback de MQTT corre en otro hilo: COM hay que inicializarlo ahi
        # y las conexiones DataSocket se abren en ese mismo hilo (afinidad de COM).
        pythoncom.CoInitialize()
        ds = DataSocket(self.cfp)
        try:
            self._procesar(payload, ds)
        finally:
            try:
                ds.cerrar()
            except Exception:
                pass
            pythoncom.CoUninitialize()

    def _procesar(self, payload, ds):
        try:
            o = json.loads(payload)
            oid = str(o["id"])
            tipo = str(o["tipo"])
        except Exception:
            return
        motivo = self.gate(ds)
        if motivo:
            self.ack(oid, "Rechazado", motivo=motivo, escrito=False)
            return

        clave = str(o.get("parametro", "")).lower() if tipo == "ParametroPid" else tipo
        if clave != "Setpoint" and clave not in MAPA and clave not in PID_URL:
            self.ack(oid, "Rechazado", motivo="DIRECCION_NO_PERMITIDA", escrito=False)
            return
        pasos = MAPA.get(clave, [])

        if tipo in ("Iniciar", "Detener"):
            valor = True
        else:
            valor = o.get("valor")
            if clave in RANGOS:
                lo, hi = RANGOS[clave]
                try:
                    valor = float(valor)
                except Exception:
                    valor = None
                if valor is None or not (lo <= valor <= hi):
                    self.ack(oid, "Rechazado", motivo="RANGO_INVALIDO", escrito=False)
                    return

        if tipo == "Setpoint":
            if str(o.get("unidad", "")).lower() != "psi":
                self.ack(oid, "Rechazado", motivo="UNIDAD_INVALIDA", escrito=False)
                return
            if ds.leer("DATOS_PAC/PC_TPM") is not True:
                self.ack(oid, "Rechazado", motivo="CONTROL_EN_HMI", escrito=False)
                return
            if ds.leer("DATOS_PAC/LED_SIST_FUN") is True or ds.leer("DATOS_PAC/ACT_VARIADOR") is True:
                self.ack(oid, "Rechazado", motivo="SETPOINT_SOLO_CON_SISTEMA_DETENIDO", escrito=False)
                return
            pasos = [("pid/setpoint_pc", valor)]

        if tipo == "ParametroPid":
            if ds.leer("DATOS_PAC/PC_TPM") is not True:
                self.ack(oid, "Rechazado", motivo="CONTROL_EN_HMI", escrito=False)
                return
            if ds.leer("DATOS_PAC/LED_SIST_FUN") is True or ds.leer("DATOS_PAC/ACT_VARIADOR") is True:
                self.ack(oid, "Rechazado", motivo="AJUSTE_SOLO_CON_SISTEMA_DETENIDO", escrito=False)
                return
            pasos = [(PID_URL[clave], valor)]

        self.ack(oid, "Aceptado", escrito=False)
        try:
            for url, v in pasos:
                ds.escribir(url, v)
                time.sleep(0.4)
            url, v = pasos[-1]
            self.ack(oid, "Escrito", escrito=True, valor_esperado=valor)
            # Dejar transcurrir varios ciclos del RT: una lectura inmediata podría
            # confirmar el eco local antes de que el controlador procese el dato.
            time.sleep(1.0 if tipo in ("Setpoint", "ParametroPid") else 0.0)
            leido = ds.leer(url)
            if leido is None:
                self.ack(oid, "Error", motivo="LECTURA_NO_CONFIRMADA", escrito=True, valor_esperado=valor)
            elif abs(float(leido) - float(v)) <= max(0.01, abs(float(v)) * 0.01):
                self.ack(oid, "Confirmado", escrito=True, valor_esperado=valor, valor_leido=leido)
            else:
                self.ack(oid, "Error", motivo="CONFIRMACION_NO_COINCIDE", escrito=True,
                         valor_esperado=valor, valor_leido=leido)
        except Exception as e:
            self.ack(oid, "Error", motivo="PLC_ERROR:" + str(e)[:120], escrito=False)


def nuevo_cliente_mqtt(cid):
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
    except AttributeError:
        return mqtt.Client(client_id=cid)


def main():
    p = argparse.ArgumentParser(description="Control de presion (cFP-2200) por variables de red")
    p.add_argument("--cfp", default="192.168.114.8")
    p.add_argument("--broker", default="192.168.114.100")
    p.add_argument("--puerto", type=int, default=1884)
    p.add_argument("--habilitado-real", action="store_true")
    a = p.parse_args()

    mq = nuevo_cliente_mqtt("control-cfp2200-{}".format(socket.gethostname()))
    mq.will_set(CTRL + "/state", json.dumps({"modo": "OFFLINE", "ts": ahora()}), qos=1, retain=True)
    mq.connect(a.broker, a.puerto, keepalive=30)
    mq.loop_start()

    ds = DataSocket(a.cfp)
    ctl = Control(ds, mq, a.habilitado_real, a.cfp)

    # Lectura periodica del estado fisico (para el gate) y de las variables de setpoint.
    mq.on_message = lambda c, u, m: ctl.procesar(m.payload.decode("utf-8", "replace"))
    mq.subscribe(CTRL + "/cmd", qos=1)
    mq.publish(CTRL + "/state", json.dumps({
        "modo": "REAL" if a.habilitado_real and os.getenv("CONTROL_PRESION_REAL") == "1" else "BLOQUEADO",
        "plc": "CONECTADO", "ts": ahora()}), qos=1, retain=True)
    print("Control de presion listo ({}). Broker mqtt://{}:{}".format(
        "REAL" if a.habilitado_real else "BLOQUEADO", a.broker, a.puerto), flush=True)

    try:
        while True:
            bombear(0.3)
            if ds.leer("DATOS_PAC/SEL_AUTO") is not None:
                ctl.ultima_lectura = time.time()
    except KeyboardInterrupt:
        print("\nDeteniendo...")
    finally:
        ds.cerrar()
        mq.publish(CTRL + "/state", json.dumps({"modo": "OFFLINE", "ts": ahora()}), qos=1, retain=True).wait_for_publish()
        mq.loop_stop()
        mq.disconnect()


if __name__ == "__main__":
    main()
