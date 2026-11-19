"""Contexto ENRIQUECIDO para el agente.

Además del resumen de la planta, entrega TODAS las señales en vivo de los 4
PLC con su significado (catálogo de los conectores edge) y el conocimiento
operativo del laboratorio.  Así el modelo puede responder modo, bomba, válvulas,
enclavamientos, PID, etc., sin inventar.

Port de ``ContextoAgente.cs``.  El catálogo de señales y el conocimiento de los
módulos se cargan de archivos de datos (``catalogo_senales.json`` y
``conocimiento_modulos.txt``), extraídos del backend original.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

HORA_LIMA = timezone(timedelta(hours=-5))

BASE = Path(__file__).resolve().parent

CONOCIMIENTO = """Conocimiento del laboratorio (USS, sala SL01LA07). Cuatro módulos didácticos INDUCONTROL, cada uno con su PLC:
- Nivel MCN-09: MicroLogix 1100 (192.168.114.9). Bomba de T1 (reserva, abajo) a T2 (acrílico, 60 cm); sensor ultrasónico mide T2; válvula Belimo de salida de T2. Selector LOCAL/REMOTO: REMOTO = manda la PC/SCADA (PID del PLC); LOCAL = manda el tablero (potenciómetro + pulsadores). T1: switch de nivel bajo I:0/2 (1 = hay agua) y switch alto I:0/3 (hipótesis).
- Caudal MCC-09: Siemens S7-200 CPU226 (192.168.114.7). Bomba con variador Altivar 11; caudalímetro Kobold 0-140 L/min; PID en el PLC (VD159 PV, VD163 SP). Selector LOCAL/REMOTO igual que nivel; M0.3 = 1 manda la HMI, 0 manda la PC. Q0.2 = sistema en marcha; Q1.1 = orden RUN al variador; Q0.0/Q0.1 = nivel alto/bajo de T1. Guardamotor GV2ME10 SIN señal al PLC: su disparo se infiere si el PLC indica marcha pero el caudal es 0 y la salida del PID está saturada (~100 %); se dispara en LOCAL con el potenciómetro al máximo.
- Presión MCP-09: NI Compact FieldPoint cFP-2200 (192.168.114.8). Bomba presuriza T2 (tanque cerrado con aire); transmisor 4-20 mA → psi; válvula proporcional de salida = perturbación. Selector MANUAL/AUTOMÁTICO.
- Temperatura MCT-09: Schneider Twido (192.168.114.10). Resistencia (PWM por relé SSR) calienta T2 principal; bomba recircula a T1 de enfriamiento (serpentín + enfriador). Switches alto/bajo en ambos tanques; un fallo de nivel detiene el lazo. Selector HMI-0-PC.
- Arquitectura: conectores edge leen los PLC → MQTT (UNS) → backend → SCADA web, lienzos y agentes MCP. Las órdenes pasan SOLO por el servicio de control con confirmación humana; tú NO ejecutas órdenes.
- Las HMI TPC-2106T originales dependían de variables compartidas NI en la PC del SCADA antiguo; hoy no forman parte del flujo.
"""


@lru_cache(maxsize=1)
def catalogo_senales() -> dict[str, list[dict[str, Any]]]:
    """Catálogo de señales por módulo (clave, descripción, unidad, hipótesis, dirección)."""
    try:
        datos = json.loads((BASE / "catalogo_senales.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:       # pragma: no cover
        log.warning("No se pudo cargar el catálogo de señales: %s", exc)
        return {}
    return datos


@lru_cache(maxsize=1)
def conocimiento_modulos() -> str:
    """Conocimiento operativo de los 4 módulos (grafo de los lienzos + mímicos)."""
    try:
        return (BASE / "conocimiento_modulos.txt").read_text(encoding="utf-8")
    except OSError as exc:                     # pragma: no cover
        log.warning("No se pudo cargar el conocimiento de los módulos: %s", exc)
        return ""


def _es_booleano(senal: dict[str, Any]) -> bool:
    """Las señales binarias se imprimen como 1/0, no como número con decimales."""
    clave = senal["clave"].lower()
    unidad = senal.get("unidad") or ""
    return (
        clave.startswith(("estado/", "io/", "falla/", "alarma/", "mando/"))
        or "/abriendo" in clave or "/cerrando" in clave
        or (not unidad and ("_on" in clave or "bajo_ok" in clave or clave.endswith("_alto")))
    )


def construir(ctx) -> str:
    """Contexto completo para el prompt del modelo."""
    lineas: list[str] = [CONOCIMIENTO, conocimiento_modulos(),
                          "Señales en vivo de cada PLC (clave = valor · significado). "
                          "[H] = significado aún en hipótesis. Booleanos: 1/ON = activo."]
    for nombre, clave_modulo in (("Nivel", "nivel-mcn09"), ("Caudal", "caudal-mcc09"),
                                 ("Presion", "presion-mcp09"),
                                 ("Temperatura", "temp-mct09")):
        lineas.append(_modulo(ctx, nombre, clave_modulo))
    return "\n".join(lineas)


def _modulo(ctx, nombre: str, clave_modulo: str) -> str:
    estado = ctx.estados.get(clave_modulo)
    if estado is None:                          # pragma: no cover
        return f"## {nombre} [{clave_modulo}] · SIN DATOS"
    ultimo = estado.ultimo_mensaje
    if ultimo is None:
        situacion = "SIN DATOS"
    else:
        edad = (datetime.now().astimezone() - ultimo).total_seconds()
        situacion = ("EN LÍNEA" if edad <= 15 else
                     f"SIN COMUNICACIÓN desde {ultimo.astimezone(HORA_LIMA):%H:%M:%S} "
                     "(los valores son viejos)")

    lineas = [f"## {nombre} [{clave_modulo}] · {situacion}"]
    for senal in catalogo_senales().get(nombre, []):
        valor = estado.numero(senal["clave"])
        if valor is None:
            continue
        if _es_booleano(senal):
            texto = "1" if valor >= 0.5 else "0"
        else:
            texto = f"{round(valor, 3):g}"
            if senal.get("unidad"):
                texto += f" {senal['unidad']}"
        desc = senal["desc"]
        if len(desc) > 110:
            desc = desc[:110] + "…"
        marca = " [H]" if senal.get("hipotesis") else ""
        lineas.append(f"- {senal['clave']} = {texto} · {desc}{marca}")
    return "\n".join(lineas)
