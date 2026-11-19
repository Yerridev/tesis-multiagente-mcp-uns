"""Cliente mínimo de OpenRouter (compatible con la API de chat de OpenAI).

La clave vive SOLO en el backend (configuración o ``OPENROUTER_API_KEY``):
jamás se expone al navegador.  Si no hay clave, el agente funciona con las
reglas deterministas.

Port de ``OpenRouterAgent.cs``.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

URL_CHAT = "https://openrouter.ai/api/v1/chat/completions"

#: Catálogo elegible desde el chat (lista cerrada: el navegador no puede pedir otro).
CATALOGO_POR_DEFECTO = (
    "nvidia/nemotron-3-ultra-550b-a55b:free|Nemotron 3 Ultra",
    "google/gemma-4-31b-it:free|Gemma 4 31B",
    "openrouter/free|Auto gratis",
)


@dataclass
class ModeloIa:
    id: str
    nombre: str
    gratis: bool


@dataclass
class LlmResultado:
    ok: bool
    model: str | None = None
    text: str | None = None
    error: str | None = None
    ms: int = 0


def _corto(modelo_id: str) -> str:
    """Nombre legible a partir del id del modelo."""
    base = modelo_id.split("/")[-1].replace(":free", "")
    partes = []
    for parte in base.split("-"):
        if not parte:
            continue
        partes.append(parte[0].upper() + parte[1:])
    return " ".join(partes)


class OpenRouterAgent:
    def __init__(self, cfg) -> None:
        self.api_key = (os.environ.get("OPENROUTER_API_KEY") or cfg.api_key or "").strip()
        self.model = (os.environ.get("OPENROUTER_MODEL") or cfg.model or "openrouter/free").strip()
        self.max_tokens = cfg.max_tokens
        self.timeout = max(10, cfg.timeout_segundos)

        self.modelos: list[ModeloIa] = []
        lista = (os.environ.get("OPENROUTER_MODELS") or "").strip()
        if not lista:
            lista = ",".join([f"{self.model}|{_corto(self.model)}", *CATALOGO_POR_DEFECTO])
        for item in (parte.strip() for parte in lista.split(",")):
            if not item:
                continue
            trozos = [t.strip() for t in item.split("|", 1)]
            modelo_id = trozos[0]
            if not modelo_id or any(m.id == modelo_id for m in self.modelos):
                continue
            nombre = trozos[1] if len(trozos) > 1 and trozos[1] else _corto(modelo_id)
            self.modelos.append(ModeloIa(modelo_id, nombre,
                                         modelo_id.endswith(":free") or modelo_id == "openrouter/free"))
        if not any(m.id == self.model for m in self.modelos):
            self.modelos.insert(0, ModeloIa(self.model, _corto(self.model),
                                            self.model.endswith(":free")))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def resolver(self, pedido: str | None) -> str:
        """Solo modelos del catálogo; cualquier otro valor usa el predeterminado."""
        if pedido and any(m.id == pedido for m in self.modelos):
            return pedido
        return self.model

    async def completar(self, sistema: str, usuario: str, historial: list | None = None,
                        modelo: str | None = None) -> LlmResultado:
        elegido = self.resolver(modelo)
        if not self.enabled:
            return LlmResultado(False, elegido, None, "sin clave de OpenRouter configurada", 0)

        payload: dict[str, Any] = {
            "model": elegido,
            "max_tokens": self.max_tokens,
            "messages": self._mensajes(sistema, usuario, historial),
        }
        cabeceras = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://127.0.0.1:5051",
            "X-Title": "MCP-Industrial",
        }
        inicio = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                respuesta = await http.post(URL_CHAT, json=payload, headers=cabeceras)
            ms = int((time.perf_counter() - inicio) * 1000)
            if respuesta.status_code != 200:
                if respuesta.status_code == 429:
                    error = "límite de consultas del modelo alcanzado (429): elige otro modelo"
                else:
                    error = f"OpenRouter respondió {respuesta.status_code}"
                return LlmResultado(False, elegido, None, error, ms)

            raiz = respuesta.json()
            modelo_real = raiz.get("model") or elegido
            texto: str | None = None
            escolhas = raiz.get("choices") or []
            if escolhas:
                mensaje = elecciones[0].get("message") or {}
                texto = mensaje.get("content")
                if not (texto or "").strip() and mensaje.get("reasoning"):
                    return LlmResultado(False, modelo_real, None,
                                        "el modelo devolvió solo razonamiento sin respuesta", ms)
            if not (texto or "").strip():
                return LlmResultado(False, modelo_real, None, "respuesta vacía del modelo", ms)
            return LlmResultado(True, modelo_real, texto.strip(), None, ms)
        except httpx.TimeoutException:
            ms = int((time.perf_counter() - inicio) * 1000)
            return LlmResultado(False, elegido, None, "tiempo de espera agotado", ms)
        except Exception as exc:
            ms = int((time.perf_counter() - inicio) * 1000)
            return LlmResultado(False, elegido, None, str(exc), ms)

    @staticmethod
    def _mensajes(sistema: str, usuario: str, historial: list | None) -> list[dict[str, str]]:
        """system + últimos turnos (máx. 8, recortados) + pregunta actual."""
        lista: list[dict[str, str]] = [{"role": "system", "content": sistema}]
        for turno in (historial or [])[-8:]:
            texto = (turno.texto if hasattr(turno, "texto") else turno.get("texto")) or ""
            if not texto.strip():
                continue
            rol = (turno.rol if hasattr(turno, "rol") else turno.get("rol")) or ""
            contenido = texto[:700] + "…" if len(texto) > 700 else texto
            lista.append({"role": "user" if str(rol).lower() == "user" else "assistant",
                          "content": contenido})
        lista.append({"role": "user", "content": usuario})
        return lista
