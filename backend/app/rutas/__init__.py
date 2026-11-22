"""Rutas de la API.

Se registran en este orden para que las rutas literales ganen a las de
parámetro (p. ej. ``/api/equipment/nivel-mcn09/signals`` antes que
``/api/equipment/{id}``), igual que en el backend de ASP.NET.
"""

from __future__ import annotations

from fastapi import FastAPI


def registrar_rutas(app: FastAPI) -> None:
    from . import agent, auth, control, equipment, lienzo, sim

    app.include_router(auth.router)
    app.include_router(equipment.router)
    app.include_router(lienzo.router)
    app.include_router(control.router)
    app.include_router(agent.router)
    app.include_router(sim.router)
