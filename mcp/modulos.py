"""Definición de los 4 módulos del laboratorio (una sola fuente para servidores MCP y agentes)."""

from __future__ import annotations

import json
from pathlib import Path

CONOCIMIENTO = Path(__file__).resolve().parent / "conocimiento"
UNS = "uss/campus/lab-automatizacion/sl01la07"

MODULOS: dict[str, dict] = {
    "nivel": {
        "equipo": "nivel-mcn09", "codigo": "MCN-09/001", "puerto": 8001,
        "plc": "Allen-Bradley MicroLogix 1100 + 1762-IF2OF2", "ip": "192.168.114.9",
        "protocolo": "EtherNet/IP (PCCC) TCP 44818",
        "variable": "Nivel del tanque T2 (cm)",
    },
    "caudal": {
        "equipo": "caudal-mcc09", "codigo": "MCC-09/002", "puerto": 8002,
        "plc": "Siemens S7-200 CPU226 + CP243-1", "ip": "192.168.114.7",
        "protocolo": "S7comm (ISO-on-TCP) TCP 102",
        "variable": "Caudal de la línea de impulsión (L/min)",
    },
    "presion": {
        "equipo": "presion-mcp09", "codigo": "MCP-09/001", "puerto": 8003,
        "plc": "NI Compact FieldPoint cFP-2200 (LabVIEW RT)", "ip": "192.168.114.8",
        "protocolo": "NI DataSocket / PSP",
        "variable": "Presión del tanque T2 (psi)",
    },
    "temperatura": {
        "equipo": "temp-mct09", "codigo": "MCT-09/001", "puerto": 8004,
        "plc": "Schneider Twido TWDLCAE40DRF + 2x TWDAMM3HT", "ip": "192.168.114.10",
        "protocolo": "Modbus TCP 502",
        "variable": "Temperatura del tanque principal (°C)",
    },
}


def conocimiento(modulo: str) -> dict:
    """Grafo + catálogo de señales + texto de conocimiento del módulo (generado de los lienzos)."""
    return json.loads((CONOCIMIENTO / f"{modulo}.json").read_text(encoding="utf-8"))
