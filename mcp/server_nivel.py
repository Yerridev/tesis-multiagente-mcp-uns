#!/usr/bin/env python3
"""
Servidor MCP (SSE) del módulo de nivel MCN-09 — SOLO LECTURA.

Expone herramientas deterministas sobre el backend ASP.NET (REST) y el knowledge
graph versionado. NO contiene ninguna herramienta de escritura ni de control:
las órdenes manuales pasan exclusivamente por el servicio determinista de control
(autenticación + auditoría + confirmación humana), nunca por MCP.

Herramientas:
  estado_actual      · valor/plc/selector/frescura del módulo
  historial          · últimas mediciones del búfer del backend
  diagnostico        · evaluación determinista (sin consigna no se inventan bandas)
  metadatos          · identificación del módulo (equipo, PLC, protocolo)
  grafo_conocimiento · knowledge graph del MCN-09 (nodos/relaciones)
  calidad_frescura   · edad del último dato y estado del edge

Transporte: SSE en MCP_NIVEL_PUERTO (por defecto 8000).
Uso:  python mcp/server_nivel.py   (BACKEND_URL=http://backend:8080)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND = os.environ.get("BACKEND_URL", "http://backend:8080").rstrip("/")
GRAFO_RUTA = Path(__file__).resolve().parent / "grafo_nivel.json"
EQUIPO = "nivel-mcn09"
FRESQUEZA_MAX_S = 30

mcp = FastMCP("mcp-nivel", host="0.0.0.0", port=int(os.environ.get("MCP_NIVEL_PUERTO", "8000")))


def _get(path: str):
    r = httpx.get(f"{BACKEND}{path}", timeout=10.0)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def estado_actual() -> dict:
    """Estado en vivo del módulo de nivel: valor, unidad, PLC, selector y timestamps."""
    equipos = _get("/api/equipment")
    eq = next((e for e in equipos if e.get("id") == EQUIPO), None)
    if eq is None:
        return {"error": "equipo no disponible en el backend"}
    return {
        "equipo": eq.get("id"),
        "nombre": eq.get("name"),
        "controlador": eq.get("controller"),
        "ip": eq.get("ip"),
        "valor": eq.get("value"),
        "unidad": eq.get("unit"),
        "consigna": eq.get("setpoint"),
        "estado": eq.get("status"),
        "alarma": eq.get("alarm"),
        "timestamp": eq.get("timestamp"),
        "solo_lectura": True,
    }


@mcp.tool()
def historial(limit: int = 120) -> list:
    """Últimas mediciones del búfer histórico del backend (máx. 600)."""
    limit = max(1, min(limit, 600))
    datos = _get(f"/api/history?equipmentId={EQUIPO}&limit={limit}")
    return datos if isinstance(datos, list) else []


@mcp.tool()
def diagnostico() -> dict:
    """Diagnóstico determinista: si no hay consigna publicada no se evalúa banda de alarma."""
    equipos = _get("/api/equipment")
    eq = next((e for e in equipos if e.get("id") == EQUIPO), None)
    if eq is None:
        return {"error": "equipo no disponible"}
    valor = eq.get("value")
    sp = eq.get("setpoint")
    online = eq.get("status") == "ONLINE"
    if not online:
        return {
            "severidad": "alarma",
            "nombre": "Sin comunicación con el PLC",
            "explicacion": "El módulo no reporta lecturas frescas; los valores mostrados corresponden a la última recepción válida.",
            "solo_lectura": True,
        }
    if not isinstance(sp, (int, float)) or sp <= 0:
        return {
            "severidad": "info",
            "nombre": "Sin consigna disponible",
            "explicacion": f"Valor actual {valor} sin consigna publicada: no se evalúa la banda de alarma.",
            "solo_lectura": True,
        }
    desv = (valor or 0) - sp
    fuera = abs(desv) > abs(sp) * 0.12
    return {
        "severidad": "alarma" if fuera else "normal",
        "nombre": "Fuera de banda" if fuera else "Operación normal",
        "explicacion": f"Valor {valor} vs consigna {sp} (desviación {desv:+.2f}).",
        "solo_lectura": True,
    }


@mcp.tool()
def metadatos() -> dict:
    """Identificación del módulo MCN-09/001 (PLC, protocolo, tópico UNS)."""
    return {
        "equipo": EQUIPO,
        "codigo": "MCN-09/001",
        "plc": "Allen-Bradley MicroLogix 1100 + 1762-IF2OF2",
        "ip": "192.168.114.9",
        "protocolo": "EtherNet/IP (PCCC) TCP 44818",
        "uns_base": f"uss/campus/lab-automatizacion/sl01la07/{EQUIPO}",
        "herramientas": "solo lectura",
    }


@mcp.tool()
def grafo_conocimiento() -> dict:
    """Knowledge graph del módulo (nodos, relaciones y layout) para explicar el proceso."""
    return json.loads(GRAFO_RUTA.read_text(encoding="utf-8"))


@mcp.tool()
def calidad_frescura() -> dict:
    """Calidad y frescura de la telemetría (edad del último dato del backend)."""
    equipos = _get("/api/equipment")
    eq = next((e for e in equipos if e.get("id") == EQUIPO), None)
    ts = (eq or {}).get("timestamp")
    edad = None
    if ts:
        try:
            when = datetime.fromisoformat(ts)
            edad = round((datetime.now(when.tzinfo) - when).total_seconds(), 1)
        except ValueError:
            edad = None
    fresca = edad is not None and edad <= FRESQUEZA_MAX_S
    return {
        "timestamp": ts,
        "edad_segundos": edad,
        "fresca": fresca,
        "max_segundos": FRESQUEZA_MAX_S,
        "estado": (eq or {}).get("status"),
        "nota": "La frescura no es requisito de arranque del servicio: reporta degradación industrial.",
    }


if __name__ == "__main__":
    print(f"[mcp-nivel] iniciando SSE en 0.0.0.0:{os.environ.get('MCP_NIVEL_PUERTO', '8000')} (solo lectura)", flush=True)
    mcp.run(transport="sse")
    sys.exit(0)
