#!/usr/bin/env python3
"""
MONITOR EN VIVO de temperatura (MCT-09): PLC -> MQTT -> WEB y WEB -> PLC, con registro.

Cada segundo muestra en pantalla y guarda en logs\\monitor-temperatura-<fecha>.csv:
  hora | PLC: cuentas, °C, SP, Kp/Ti/Td, salida PID, resistencia, marcha | WEB: °C, SP, estado | DIFERENCIA
Ademas registra al instante en logs\\monitor-temperatura-<fecha>.log:
  - cada ORDEN que la web manda al PLC (topico .../control/cmd)
  - cada RESPUESTA del PLC (topico .../control/ack)
  - cada lectura de TERMOMETRO que escribas (numero + Enter) -> para calibrar

Solo lectura: no envia nada al PLC.  Ctrl+C para terminar.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt

RAIZ = Path(__file__).resolve().parents[2]
BASE = "uss/campus/lab-automatizacion/sl01la07/temperatura-mct09"
WEB = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
EQUIPO = "temp-mct09"


def env(clave: str) -> str:
    try:
        for l in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
            if l.startswith(clave + "="):
                return l.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


TOKEN = env("SERVICIO_TOKEN")
plc: dict[str, object] = {}          # ultimo valor publicado por el lector del Twido (clave -> valor)
lock = threading.Lock()
ahora = lambda: datetime.now().strftime("%H:%M:%S")  # noqa: E731
stamp = datetime.now().strftime("%Y%m%d-%H%M")
(RAIZ / "logs").mkdir(exist_ok=True)
f_csv = open(RAIZ / "logs" / f"monitor-temperatura-{stamp}.csv", "w", newline="", encoding="utf-8-sig")
f_log = open(RAIZ / "logs" / f"monitor-temperatura-{stamp}.log", "a", encoding="utf-8")
w = csv.writer(f_csv, delimiter=";")
w.writerow(["hora", "plc_cuentas", "plc_c", "web_c", "dif_c", "plc_sp_c", "web_sp_c", "kp", "ti", "td",
            "salida_pid_pct", "resistencia", "marcha", "bomba", "web_estado", "termometro_c"])
termometro: list[float | None] = [None]


def evento(texto: str) -> None:
    linea = f"[{ahora()}] {texto}"
    print("\n  >> " + linea, flush=True)
    f_log.write(linea + "\n"); f_log.flush()


def on_message(_c, _u, m):
    t = m.topic
    try:
        txt = m.payload.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return
    if t.endswith("/control/cmd"):
        try:
            d = json.loads(txt)
            evento(f"WEB -> PLC  ORDEN  {d.get('tipo')} {d.get('parametro') or ''} {d.get('valor') if d.get('valor') is not None else ''}  usuario={d.get('usuario')}  id={str(d.get('id'))[:8]}")
        except ValueError:
            evento(f"WEB -> PLC  ORDEN  {txt[:200]}")
        return
    if t.endswith("/control/ack"):
        try:
            d = json.loads(txt)
            evento(f"PLC -> WEB  RESPUESTA  estado={d.get('estado')}  leido={d.get('valor_leido', d.get('leido', d.get('valorLeido')))}  motivo={d.get('motivo') or ''}  id={str(d.get('id'))[:8]}")
        except ValueError:
            evento(f"PLC -> WEB  RESPUESTA  {txt[:200]}")
        return
    if "/funcional/" in t:
        clave = t.split("/funcional/", 1)[1]
        try:
            v = json.loads(txt)
            v = v.get("value") if isinstance(v, dict) else v
        except ValueError:
            v = txt.strip()
        with lock:
            plc[clave] = v


def conectar_mqtt() -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"monitor-temp-{os.getpid()}")
    c.on_message = on_message
    c.on_connect = lambda cli, *_a: cli.subscribe(BASE + "/#", qos=0)
    for host in ("192.168.114.100", "127.0.0.1"):
        try:
            c.connect(host, 1884, keepalive=30)
            c.loop_start()
            print(f"MQTT: conectado a {host}:1884 (broker del stack)")
            return c
        except OSError:
            continue
    print("No pude conectar al broker 1884 (¿stack levantado?)"); sys.exit(1)


def leer_teclado():
    while True:
        try:
            s = input().strip().replace(",", ".")
        except EOFError:
            return
        try:
            termometro[0] = float(s)
            evento(f"TERMOMETRO  {termometro[0]} °C  (PLC cuentas={plc.get('temperatura/principal_raw')}  web={plc.get('temperatura/principal_c')})")
        except ValueError:
            pass


def f(v, n=2):
    return f"{v:.{n}f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else ("-" if v is None else str(v))


def si(v):
    return "ON " if v is True else ("off" if v is False else " - ")


def main():
    conectar_mqtt()
    threading.Thread(target=leer_teclado, daemon=True).start()
    cab = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    print("Escribe la temperatura del TERMOMETRO + Enter cuando la midas (queda registrada).  Ctrl+C = salir")
    print(f"{'hora':8} | {'PLC cnt':>7} {'PLC °C':>7} {'WEB °C':>7} {'dif':>5} | {'SP plc':>6} {'SP web':>6} | {'Kp':>5} {'Ti':>4} {'Td':>4} | {'PID%':>5} res marcha bomba | web")
    while True:
        web_c = web_sp = web_estado = None
        try:
            eq = httpx.get(f"{WEB}/api/equipment/{EQUIPO}", headers=cab, timeout=3).json()
            web_c, web_sp, web_estado = eq.get("value"), eq.get("setpoint"), eq.get("status")
        except Exception:  # noqa: BLE001
            web_estado = "SIN WEB"
        with lock:
            p = dict(plc)
        pc = p.get("temperatura/principal_c")
        dif = (web_c - pc) if isinstance(web_c, (int, float)) and isinstance(pc, (int, float)) else None
        fila = [ahora(), p.get("temperatura/principal_raw"), pc, web_c, None if dif is None else round(dif, 2),
                p.get("pid/setpoint_c"), web_sp, p.get("pid/kp"), p.get("pid/ti"), p.get("pid/td"),
                p.get("pid/salida_pct"), p.get("estado/resistencia_on"), p.get("estado/sistema_funcionando"),
                p.get("estado/bomba_marcha"), web_estado, termometro[0]]
        w.writerow(fila); f_csv.flush()
        alerta = "  <-- WEB != PLC" if dif is not None and abs(dif) > 0.5 else ""
        print(f"{fila[0]:8} | {f(fila[1],0):>7} {f(pc):>7} {f(web_c):>7} {f(dif,1):>5} | {f(fila[5],1):>6} {f(web_sp,1):>6} | "
              f"{f(fila[7],0):>5} {f(fila[8],0):>4} {f(fila[9],0):>4} | {f(fila[10],1):>5} {si(fila[11])} {si(fila[12])}    {si(fila[13])}  | {web_estado}{alerta}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor detenido. Registros en la carpeta logs\\ (monitor-temperatura-*.csv y .log)")
