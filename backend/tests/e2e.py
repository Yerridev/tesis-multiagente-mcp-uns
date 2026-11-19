"""Prueba de extremo a extremo del backend Python.

Levanta el backend contra un broker MQTT aislado, publica telemetría de los
cuatro módulos y comprueba que:

1. la telemetría llega al estado de la planta (REST);
2. el canal SSE empuja ``telemetry`` con el valor recibido;
3. las señales del módulo llegan por SSE con el mismo formato que antes.

Uso::

    python tests/e2e.py --mqtt 127.0.0.1 --puerto 18830
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx                                                    # noqa: E402
import paho.mqtt.client as mqtt                                # noqa: E402

UNS = "uss/campus/lab-automatizacion/sl01la07"

#: (tópico relativo, payload JSON) que publica el "conector edge" de prueba.
TELEMETRIA = [
    ("nivel-mcn09/funcional/nivel/raw",
     {"value": 16548, "unit": "cuentas", "source": "edge-ml1100/N7:4", "tag": "NIVEL_RAW"}),
    ("nivel-mcn09/funcional/nivel/cm",
     {"value": 12.5, "unit": "cm", "source": "edge-ml1100/N7:4", "tag": "NIVEL_CM"}),
    ("nivel-mcn09/funcional/nivel/pct",
     {"value": 20.8, "unit": "%", "source": "edge-ml1100/N7:4", "tag": "NIVEL_PCT"}),
    ("nivel-mcn09/funcional/nivel/fuera_rango_sensor",
     {"value": False, "source": "edge-ml1100/N7:4", "tag": "NIVEL_FUERA"}),
    ("nivel-mcn09/funcional/estado/selector_remoto", {"value": True, "tag": "SEL_REMOTO"}),
    ("nivel-mcn09/funcional/estado/selector_local", {"value": False, "tag": "SEL_LOCAL"}),
    ("nivel-mcn09/funcional/estado/fuente_control", {"value": "PC", "tag": "FUENTE"}),
    ("nivel-mcn09/funcional/estado/bomba_marcha", {"value": True, "tag": "BOMBA"}),
    ("nivel-mcn09/funcional/bomba/frecuencia_estimada_hz",
     {"value": 33.0, "unit": "Hz", "tag": "HZ"}),
    ("nivel-mcn09/funcional/pid/setpoint_a_raw", {"value": 11348, "unit": "cuentas", "tag": "SP"}),
    ("nivel-mcn09/funcional/plc/conexion", "CONECTADO"),
    ("nivel-mcn09/funcional/edge/estado", "ONLINE"),
    ("caudal-mcc09/funcional/caudal/caudalimetro",
     {"value": 88.4, "unit": "L/min", "tag": "CAUDAL"}),
    ("caudal-mcc09/funcional/caudal/setpoint", {"value": 90.0, "unit": "L/min", "tag": "SP_C"}),
    ("caudal-mcc09/funcional/estado/selector_remoto", {"value": True, "tag": "SEL_REMOTO"}),
    ("caudal-mcc09/funcional/estado/selector_local", {"value": False, "tag": "SEL_LOCAL"}),
    ("caudal-mcc09/funcional/plc/conexion", "CONECTADO"),
    ("presion-mcp09/funcional/presion/psi", {"value": 21.7, "unit": "psi", "tag": "PSI"}),
    ("presion-mcp09/funcional/pid/setpoint_pc", {"value": 22.0, "unit": "psi", "tag": "SP_P"}),
    ("presion-mcp09/funcional/estado/selector_remoto", {"value": True, "tag": "SEL_REMOTO"}),
    ("presion-mcp09/funcional/estado/selector_local", {"value": False, "tag": "SEL_LOCAL"}),
    ("presion-mcp09/funcional/plc/conexion", "CONECTADO"),
    ("temperatura-mct09/funcional/temperatura/principal_c", {"value": 38.4, "unit": "C", "tag": "TEMP"}),
    ("temperatura-mct09/funcional/pid/setpoint_c", {"value": 40.0, "unit": "C", "tag": "SP_T"}),
    ("temperatura-mct09/funcional/estado/selector_remoto", {"value": True, "tag": "SEL_REMOTO"}),
    ("temperatura-mct09/funcional/estado/selector_local", {"value": False, "tag": "SEL_LOCAL"}),
    ("temperatura-mct09/funcional/plc/conexion", "CONECTADO"),
]


async def _leer_eventos(url: str, segundos: float) -> dict:
    """Lee el stream SSE y acumula los eventos por nombre."""
    eventos: dict = {}
    limite = asyncio.get_running_loop().time() + segundos
    async with httpx.AsyncClient(timeout=segundos + 5) as http:
        async with http.stream("GET", url) as respuesta:
            assert respuesta.status_code == 200, respuesta.status_code
            async for linea in respuesta.aiter_lines():
                if asyncio.get_running_loop().time() > limite:
                    break
                if linea.startswith("event: "):
                    nombre = linea[len("event: "):]
                elif linea.startswith("data: ") and nombre:
                    try:
                        eventos.setdefault(nombre, []).append(json.loads(linea[len("data: "):]))
                    except ValueError:
                        pass
    return eventos


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mqtt", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=18830)
    parser.add_argument("--api", default="http://127.0.0.1:5099")
    args = parser.parse_args()

    # 1) el backend (en proceso, con la configuración del broker de prueba)
    os.environ["Mqtt__Host"] = args.mqtt
    os.environ["Mqtt__Port"] = str(args.puerto)
    os.environ["Auth__Habilitado"] = "false"
    os.environ["Health__DatabaseEnabled"] = "false"

    import uvicorn

    from app.main import crear_app

    config_app = uvicorn.Config(crear_app(), host="127.0.0.1", port=5099, log_level="warning")
    servidor = uvicorn.Server(config_app)
    tarea = asyncio.create_task(servidor.serve())
    while not servidor.started:
        await asyncio.sleep(0.1)
    print("· backend levantado en", args.api)

    fallos: list[str] = []
    try:
        # 2) el "conector edge" publica la telemetría
        cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e-edge")
        cliente.connect(args.mqtt, args.puerto, keepalive=30)
        cliente.loop_start()
        for relativo, payload in TELEMETRIA:
            cuerpo = payload if isinstance(payload, str) else json.dumps(payload)
            cliente.publish(f"{UNS}/{relativo}", cuerpo, qos=1, retain=True)
        cliente.loop_stop()
        cliente.disconnect()
        print(f"· publicados {len(TELEMETRIA)} mensajes MQTT")

        await asyncio.sleep(2.0)

        async with httpx.AsyncClient(timeout=15) as http:
            # 3) el estado de la planta ya trae los valores reales
            equipos = (await http.get(f"{args.api}/api/equipment")).json()
            por_id = {e["id"]: e for e in equipos}
            print("· /api/equipment:")
            for e in equipos:
                print(f"    {e['id']:<15} {e['value']} {e['unit']:<6} "
                      f"consigna={e['setpoint']} {e['status']} calidad={e['calidad']}")

            if por_id["nivel-mcn09"]["value"] != 12.5:
                fallos.append(f"nivel: esperaba 12.5, llegó {por_id['nivel-mcn09']['value']}")
            if por_id["caudal-mcc09"]["value"] != 88.4:
                fallos.append(f"caudal: esperaba 88.4, llegó {por_id['caudal-mcc09']['value']}")
            if por_id["presion-mcp09"]["value"] != 21.7:
                fallos.append(f"presion: esperaba 21.7, llegó {por_id['presion-mcp09']['value']}")
            if por_id["temp-mct09"]["value"] != 38.4:
                fallos.append(f"temperatura: esperaba 38.4, llegó {por_id['temp-mct09']['value']}")
            if por_id["nivel-mcn09"]["status"] != "ONLINE":
                fallos.append(f"nivel: esperaba ONLINE, llegó {por_id['nivel-mcn09']['status']}")

            # 4) el detalle del nivel (consigna en cm desde N7:5)
            detalle = (await http.get(f"{args.api}/api/equipment/nivel-mcn09/detail")).json()
            print("· detalle nivel:", json.dumps(
                {k: detalle[k] for k in ("level", "setpoint", "percent", "pumpOn", "mode", "calidad")},
                ensure_ascii=False))
            if detalle["level"] != 12.5:
                fallos.append(f"detalle nivel: esperaba 12.5, llegó {detalle['level']}")
            if detalle["setpoint"] != 12.5:
                fallos.append(f"consigna: esperaba 12.5, llegó {detalle['setpoint']}")

            # 5) las señales crudas
            senales = (await http.get(f"{args.api}/api/equipment/nivel-mcn09/signals")).json()
            if senales["temaBase"] != f"{UNS}/nivel-mcn09":
                fallos.append(f"temaBase: {senales['temaBase']}")
            if "nivel/cm" not in senales["valores"]:
                fallos.append("faltan las señales crudas del nivel")

            # 6) el canal SSE
            eventos = await _leer_eventos(f"{args.api}/api/stream", 3.0)
            print("· eventos SSE recibidos:", ", ".join(sorted(eventos)))
            for obligatorio in ("telemetry", "nivelSenales", "caudalSenales",
                                "presionSenales", "temperaturaSenales"):
                if obligatorio not in eventos:
                    fallos.append(f"SSE: no llegó el evento {obligatorio}")
            if "telemetry" in eventos:
                ultimo = eventos["telemetry"][-1]
                ids = {e["id"]: e for e in ultimo}
                print("· SSE telemetry (último envío):")
                for e in ultimo:
                    print(f"    {e['id']:<15} {e['value']} {e['unit']}")
                if ids.get("nivel-mcn09", {}).get("value") != 12.5:
                    fallos.append("SSE: el valor del nivel no llegó en el evento telemetry")
            if "nivelSenales" in eventos:
                valores = eventos["nivelSenales"][-1]["valores"]
                if "nivel/cm" not in valores:
                    fallos.append("SSE: nivelSenales sin la señal nivel/cm")

            # 7) el historial ya tiene muestras
            historial = (await http.get(f"{args.api}/api/history?limit=100")).json()
            print(f"· historial: {len(historial)} muestras")
            if not historial:
                fallos.append("el historial está vacío")

            # 8) el control responde (dry-run, sin broker de control)
            control = await http.get(f"{args.api}/api/control/estado",
                                     headers={"Authorization": "Bearer dev-supervisor"})
            if control.status_code != 200:
                fallos.append(f"control/estado: HTTP {control.status_code}")
            else:
                print("· control:", control.json()["datos"]["modoEfectivo"])

    finally:
        servidor.should_exit = True
        await tarea

    print()
    if fallos:
        print("FALLOS:")
        for f in fallos:
            print("  ·", f)
        return 1
    print("OK · extremo a extremo correcto")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
