"""Escenarios: eventos programados en tiempo simulado (segundos) para pruebas repetibles."""
from __future__ import annotations

import json
from pathlib import Path

ACCIONES_ENTRADA = {"selector", "nivel_alto_principal", "nivel_bajo_principal_ok",
                    "nivel_alto_enfriador", "nivel_bajo_enfriador_ok"}
ACCIONES_PLANTA = {"sensor_congelado", "t_ambiente"}
ACCIONES_PLC = {"plc_desconectado", "escribir_mw", "escribir_m"}


def cargar(ruta: str | Path, acciones: set[str] | None = None) -> dict:
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    eventos = sorted(datos.get("eventos", []), key=lambda ev: ev["t"])
    for ev in eventos:
        a = ev.get("accion")
        if a not in (acciones or ACCIONES_ENTRADA | ACCIONES_PLANTA | ACCIONES_PLC):
            raise ValueError(f"accion desconocida en el escenario: {a}")
    datos["eventos"] = eventos
    return datos


class Reproductor:
    def __init__(self, escenario: dict | None):
        self.eventos = list(escenario["eventos"]) if escenario else []
        self.nombre = escenario.get("nombre", "") if escenario else ""

    def pendientes(self, t: float) -> list[dict]:
        listos = [ev for ev in self.eventos if ev["t"] <= t]
        self.eventos = [ev for ev in self.eventos if ev["t"] > t]
        return listos
