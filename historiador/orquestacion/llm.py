"""
Cliente LLM comun para todas las configuraciones (API compatible con OpenAI: Gemini, Ollama, Anthropic, etc.).
- Mismo cliente, misma temperatura y mismos topes para A, B y C: la unica variable es la arquitectura.
- Respeta un ritmo maximo de peticiones por minuto (nivel gratuito de Gemini) y reintenta ante 429/5xx.
- Acumula el uso (peticiones, tokens, segundos) en el objeto Uso que se le pase.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PERFILES_PATH = Path(__file__).resolve().parent / "modelos.json"


@dataclass
class Uso:
    peticiones: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    segundos_llm: float = 0.0
    reintentos: int = 0
    por_agente: dict = field(default_factory=dict)

    def sumar(self, agente: str, entrada: int, salida: int, segundos: float) -> None:
        self.peticiones += 1
        self.tokens_entrada += entrada
        self.tokens_salida += salida
        self.segundos_llm += segundos
        a = self.por_agente.setdefault(agente, {"peticiones": 0, "tokens_entrada": 0, "tokens_salida": 0})
        a["peticiones"] += 1
        a["tokens_entrada"] += entrada
        a["tokens_salida"] += salida

    def resumen(self) -> dict:
        return {"peticiones": self.peticiones, "tokens_entrada": self.tokens_entrada,
                "tokens_salida": self.tokens_salida, "tokens_total": self.tokens_entrada + self.tokens_salida,
                "segundos_llm": round(self.segundos_llm, 2), "reintentos": self.reintentos,
                "por_agente": self.por_agente}


def cargar_perfiles() -> dict:
    return json.loads(PERFILES_PATH.read_text(encoding="utf-8"))["perfiles"]


class ClienteLLM:
    def __init__(self, nombre_perfil: str):
        from openai import AsyncOpenAI

        perfiles = cargar_perfiles()
        if nombre_perfil not in perfiles:
            raise ValueError(f"Perfil '{nombre_perfil}' no existe en modelos.json. Opciones: {', '.join(perfiles)}")
        p = perfiles[nombre_perfil]
        self.perfil = nombre_perfil
        clave_env = p.get("clave_env")
        clave = os.getenv(clave_env, "") if clave_env else "no-requerida"
        if clave_env and not clave:
            raise RuntimeError(f"Falta {clave_env} en el .env del historiador (perfil {nombre_perfil})")
        self.modelo = (os.getenv(p["modelo_env"], "") if p.get("modelo_env") else "") or p["modelo"]
        self.temperatura = float(p.get("temperatura", 0.0))
        self.max_tokens = int(p.get("max_tokens", 2048))
        self.min_intervalo = 60.0 / float(p["rpm"]) if p.get("rpm") else 0.0
        self.esquema_gemini = bool(p.get("esquema_gemini", False))
        self.cliente = AsyncOpenAI(api_key=clave, base_url=p["base_url"], timeout=float(p.get("timeout_s", 120)))
        self._ultimo = 0.0
        self._candado = asyncio.Lock()

    async def _turno(self) -> None:
        """Espacia las peticiones segun el rpm del perfil (tambien entre agentes en paralelo)."""
        if not self.min_intervalo:
            return
        async with self._candado:
            espera = self._ultimo + self.min_intervalo - time.monotonic()
            if espera > 0:
                await asyncio.sleep(espera)
            self._ultimo = time.monotonic()

    async def chat(self, mensajes: list[dict], uso: Uso, agente: str,
                   herramientas: list[dict] | None = None) -> Any:
        """Una peticion al modelo. Devuelve el mensaje (con .content y .tool_calls)."""
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

        args: dict[str, Any] = {"model": self.modelo, "messages": mensajes, "temperature": self.temperatura,
                                "max_tokens": self.max_tokens}
        if herramientas:
            args["tools"] = herramientas
            args["tool_choice"] = "auto"
        esperas = [5, 15, 30, 60, 90]
        for intento in range(len(esperas) + 1):
            await self._turno()
            t0 = time.perf_counter()
            try:
                resp = await self.cliente.chat.completions.create(**args)
            except (RateLimitError, APITimeoutError, APIConnectionError):
                if intento == len(esperas):
                    raise
                uso.reintentos += 1
                await asyncio.sleep(esperas[intento] + random.random())
                continue
            except APIStatusError as e:
                if e.status_code >= 500 and intento < len(esperas):
                    uso.reintentos += 1
                    await asyncio.sleep(esperas[intento] + random.random())
                    continue
                raise
            u = getattr(resp, "usage", None)
            uso.sumar(agente, getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0,
                      time.perf_counter() - t0)
            return resp.choices[0].message
        raise RuntimeError("sin respuesta del modelo")
