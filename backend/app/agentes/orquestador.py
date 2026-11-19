"""Puente del chat web hacia el SISTEMA MULTIAGENTE MCP (Python).

Publica la pregunta en ``{UNS}/agentes/orquestador/solicitud`` y espera la
respuesta en ``.../respuesta``.  El orquestador publica su estado retenido en
``.../estado`` (``en_linea`` / ``fuera_de_linea``) y el catálogo de servidores
MCP en ``{UNS}/agentes/catalogo``.

Port de ``OrquestadorMultiagente.cs``.  Mejora sobre el original: se mantiene
**una sola conexión MQTT** en vez de abrir una por petición (el frontend
consulta el catálogo cada 15 s).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import paho.mqtt.client as mqtt

from ..modulos import UNS

log = logging.getLogger(__name__)

TOPICO_BASE = f"{UNS}/agentes/orquestador"


class OrquestadorMultiagente:
    def __init__(self, cfg) -> None:
        self.host = cfg.mqtt.host_agentes
        self.puerto = cfg.mqtt.port_agentes
        self.espera = cfg.agente_multiagente_timeout
        self._cliente: mqtt.Client | None = None
        self._lock = asyncio.Lock()
        self._pendientes: dict[str, asyncio.Future] = {}
        self._catalogo: dict[str, Any] | None = None
        self._en_linea = False
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ conexión
    async def _conectar(self) -> mqtt.Client | None:
        async with self._lock:
            if self._cliente is not None and self._cliente.is_connected():
                return self._cliente
            if self._cliente is not None:
                try:
                    self._cliente.loop_stop()
                    self._cliente.disconnect()
                except Exception:                # pragma: no cover
                    pass
                self._cliente = None

            loop = asyncio.get_running_loop()
            self._loop = loop
            cliente = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"backend-chat-{uuid.uuid4().hex[:8]}",
            )
            cliente.reconnect_delay_set(1, 10)

            def _on_connect(cli, _u, _f, reason_code, _p=None):
                if getattr(reason_code, "is_failure", False):
                    log.warning("Orquestador: MQTT rechazó la conexión (%s)", reason_code)
                    return
                cli.subscribe(f"{TOPICO_BASE}/estado", qos=1)
                cli.subscribe(f"{TOPICO_BASE}/respuesta", qos=1)
                cli.subscribe(f"{UNS}/agentes/catalogo", qos=1)
                log.info("Orquestador: MQTT conectado a %s:%s", self.host, self.puerto)

            def _on_message(_cli, _u, mensaje):
                try:
                    raiz = json.loads(mensaje.payload.decode("utf-8", errors="replace"))
                except ValueError:
                    return
                if not isinstance(raiz, dict):
                    return
                if mensaje.topic.endswith("/estado"):
                    loop.call_soon_threadsafe(self._set_en_linea,
                                              raiz.get("estado") == "en_linea")
                elif mensaje.topic.endswith("/catalogo"):
                    loop.call_soon_threadsafe(self._set_catalogo, raiz)
                elif mensaje.topic.endswith("/respuesta"):
                    id_solicitud = raiz.get("id_solicitud")
                    if id_solicitud:
                        loop.call_soon_threadsafe(self._resolver, id_solicitud, raiz)

            cliente.on_connect = _on_connect
            cliente.on_message = _on_message
            cliente.on_disconnect = lambda *_a, **_k: loop.call_soon_threadsafe(
                self._set_en_linea, False)

            try:
                cliente.connect(self.host, self.puerto, keepalive=30)
            except OSError as exc:
                log.warning("Orquestador: MQTT no disponible (%s:%s) — %s",
                            self.host, self.puerto, exc)
                return None
            cliente.loop_start()
            self._cliente = cliente
            # Da tiempo a que llegue el estado retenido.
            await asyncio.sleep(0.4)
            return cliente

    def _set_en_linea(self, valor: bool) -> None:
        self._en_linea = valor

    def _set_catalogo(self, catalogo: dict[str, Any]) -> None:
        self._catalogo = catalogo

    def _resolver(self, id_solicitud: str, respuesta: dict[str, Any]) -> None:
        futuro = self._pendientes.get(id_solicitud)
        if futuro is not None and not futuro.done():
            futuro.set_result(respuesta)

    # ------------------------------------------------------------------ consultas
    async def catalogo(self) -> dict[str, Any] | None:
        """Catálogo retenido que publica el orquestador cada 15 s."""
        await self._conectar()
        return self._catalogo

    async def en_linea(self) -> bool:
        """¿Está corriendo el orquestador?"""
        await self._conectar()
        return self._en_linea

    async def preguntar(self, pregunta: str, historial: list | None = None,
                        modelo: str | None = None, usuario: str | None = None) -> dict[str, Any] | None:
        """None si el sistema multiagente no está corriendo o no respondió a tiempo."""
        cliente = await self._conectar()
        if cliente is None:
            return None
        if not self._en_linea:
            return None

        id_solicitud = uuid.uuid4().hex[:12]
        futuro: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pendientes[id_solicitud] = futuro
        try:
            cuerpo = json.dumps({
                "id": id_solicitud,
                "pregunta": pregunta,
                "origen": f"chat-web:{usuario or 'anonimo'}",
                "modelo": modelo,
                "historial": [
                    {"rol": t.rol, "texto": t.texto}
                    for t in (historial or [])[-6:]
                    if getattr(t, "texto", None)
                ],
            }, ensure_ascii=False)
            cliente.publish(f"{TOPICO_BASE}/solicitud", cuerpo, qos=1)
            try:
                return await asyncio.wait_for(futuro, timeout=self.espera)
            except asyncio.TimeoutError:
                log.warning("Orquestador: sin respuesta en %s s", self.espera)
                return None
        finally:
            self._pendientes.pop(id_solicitud, None)

    # ------------------------------------------------------------------ conversión
    @staticmethod
    def convertir(respuesta: dict[str, Any]) -> dict[str, Any]:
        """Respuesta del orquestador → formato del chat, con la traza completa."""
        traza: list[dict[str, Any]] = []

        def _texto(raiz: dict[str, Any], campo: str) -> str:
            valor = raiz.get(campo)
            return valor if isinstance(valor, str) else ""

        def _numero(raiz: dict[str, Any], campo: str) -> int:
            valor = raiz.get(campo)
            return int(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else 0

        plan = respuesta.get("plan")
        modulos = ", ".join(plan.keys()) if isinstance(plan, dict) else ""
        traza.append({"name": "interprete", "ok": True, "ms": 0,
                      "result": f"{_texto(respuesta, 'interprete')} · módulos: {modulos}"})

        for informe in respuesta.get("informes") or []:
            if not isinstance(informe, dict):
                continue
            modulo = _texto(informe, "modulo")
            for herramienta in informe.get("herramientas") or []:
                if not isinstance(herramienta, dict):
                    continue
                traza.append({
                    "name": f"mcp-{modulo}.{_texto(herramienta, 'herramienta')}",
                    "ok": bool(herramienta.get("ok")),
                    "ms": _numero(herramienta, "ms"),
                    "result": "",
                })
            traza.append({
                "name": f"analista-{modulo}",
                "ok": _texto(informe, "modo") != "error",
                "ms": _numero(informe, "ms"),
                "result": f"{_texto(informe, 'severidad')} · {_texto(informe, 'modo')}",
            })

        for modulo in respuesta.get("sin_respuesta") or []:
            traza.append({"name": f"analista-{modulo}", "ok": False, "ms": 0,
                          "result": "no respondió a tiempo"})

        veredicto = respuesta.get("veredicto") or {}
        traza.append({
            "name": "veredicto", "ok": True, "ms": _numero(veredicto, "ms"),
            "result": f"severidad {_texto(veredicto, 'severidad')} · {_texto(veredicto, 'modo')}",
        })
        modelo = _texto(veredicto, "modelo")
        return {
            "reply": _texto(veredicto, "respuesta"),
            "agent": "Sistema multiagente MCP · orquestador",
            "tools": traza,
            "mode": "multiagente",
            "model": modelo or None,
        }
