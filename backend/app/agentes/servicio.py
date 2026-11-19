"""Servicio del agente de supervisión.

Combina las herramientas deterministas (solo lectura) con un modelo de
OpenRouter cuando hay clave configurada.  Si el modelo falla, responde con la
lógica de reglas y lo indica en la traza.

Antes del modelo propio se consulta el SISTEMA MULTIAGENTE MCP (orquestador
Python): si está corriendo, su respuesta es la que se devuelve; si no, se avisa
y responde el agente clásico.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from . import reglas
from .conversaciones import ConversacionesStore
from .openrouter import OpenRouterAgent
from .orquestador import OrquestadorMultiagente

log = logging.getLogger(__name__)


class AgenteService:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.llm = OpenRouterAgent(ctx.cfg.openrouter)
        self.multi = OrquestadorMultiagente(ctx.cfg)
        self.chats = ConversacionesStore(ctx.cfg.agente_conversaciones_ruta)

    async def arrancar(self) -> None:
        """Prepara el puente con el orquestador (conexión perezosa)."""
        try:
            await self.multi._conectar()
        except Exception:                       # pragma: no cover
            log.debug("El orquestador multiagente aún no está disponible")

    # ------------------------------------------------------------------ estado
    def status(self) -> dict[str, Any]:
        return {
            "mode": "llm" if self.llm.enabled else "rules",
            "enabled": self.llm.enabled,
            "model": self.llm.model,
            "models": [{"id": m.id, "nombre": m.nombre, "gratis": m.gratis}
                       for m in self.llm.modelos],
            "provider": "OpenRouter",
            "scope": "solo lectura · sin escritura al PLC",
        }

    # ------------------------------------------------------------------ pregunta
    async def preguntar(self, mensaje: str | None, historial: list | None = None,
                        modelo: str | None = None, usuario: str | None = None) -> dict[str, Any]:
        """Responde una pregunta del chat.

        1º el SISTEMA MULTIAGENTE MCP (Python); si no está corriendo, el agente
        clásico (reglas deterministas + OpenRouter).
        """
        pregunta = (mensaje or "").strip() or "¿Cómo está la planta ahora?"

        try:
            respuesta_multi = await self.multi.preguntar(pregunta, historial, modelo, usuario)
        except Exception as exc:                # pragma: no cover
            log.warning("Sistema multiagente no disponible: %s", exc)
            respuesta_multi = None

        if respuesta_multi:
            respuesta = self.multi.convertir(respuesta_multi)
        else:
            respuesta = await self._agente_clasico(pregunta, historial, modelo)

        respuesta["ts"] = datetime.now().astimezone()
        return respuesta

    async def _agente_clasico(self, pregunta: str, historial: list | None,
                              modelo: str | None) -> dict[str, Any]:
        base = reglas.preguntar(self.ctx.planta, pregunta)
        if not self.llm.enabled:
            base["mode"] = "rules"
            return base

        sistema = (reglas.contexto_sistema(self.ctx.planta) + "\n" + reglas.REGLAS
                   + "\n" + self._contexto_extra())
        resultado = await self.llm.completar(sistema, pregunta, historial, modelo)

        traza = list(base["tools"])
        traza.append({
            "name": "consulta_openrouter",
            "ok": resultado.ok,
            "ms": resultado.ms,
            "result": f"modelo {resultado.model}" if resultado.ok
                      else (resultado.error or "sin respuesta"),
        })

        if not resultado.ok:
            # Se AVISA que la IA no respondió (límite diario, modelo caído...) y por qué;
            # la respuesta que sigue es la de reglas deterministas, no la del modelo.
            base["reply"] = (f"⚠️ La IA no respondió ({resultado.error or 'sin respuesta'}). "
                             f"Respuesta automática por reglas:\n{base['reply']}")
            base["tools"] = traza
            base["mode"] = "rules"
            base["model"] = None
            return base

        base["reply"] = resultado.text or ""
        base["agent"] = "Agente de supervisión · OpenRouter"
        base["tools"] = traza
        base["mode"] = "llm"
        base["model"] = resultado.model
        return base

    def _contexto_extra(self) -> str:
        """Contexto enriquecido: conocimiento del laboratorio + señales vivas."""
        from . import contexto

        return contexto.construir(self.ctx)
