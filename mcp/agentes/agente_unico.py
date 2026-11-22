#!/usr/bin/env python3
"""
Configuración A — AGENTE ÚNICO (línea base del experimento).

Un solo agente basado en LLM con acceso directo a las 28 herramientas de los 4 servidores MCP
(mismos servidores, mismo modelo y misma temperatura que el sistema multiagente). No hay
orquestador ni analistas: el propio agente decide qué herramientas usar y redacta la respuesta.
Solo lectura: las herramientas MCP no escriben en los PLC.

Uso:  python mcp/agentes/agente_unico.py "¿cómo está la planta?"
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession
from mcp.client.sse import sse_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import LLM, MODULOS, ahora, nuevo_id, traza, url_mcp  # noqa: E402

MAX_PASOS = 10          # el doble que un analista: debe cubrir los 4 módulos él solo
MAX_TEXTO = 7000
SEP = "__"              # nombre de herramienta = <modulo>__<herramienta>

PERFIL = (
    "Eres el agente de un laboratorio industrial con 4 módulos: nivel, caudal, presion y temperatura. "
    "Tienes herramientas MCP de SOLO LECTURA para cada módulo; su nombre empieza con el módulo "
    "(por ejemplo caudal__diagnostico). Usa las herramientas necesarias para responder la pregunta del "
    "operador. Reglas: no inventes valores; si un dato no existe dilo; cita los valores que usaste con su "
    "unidad. Responde en español, claro y breve (máx. 10 líneas)."
)


def _texto(resultado) -> str:
    return "\n".join(getattr(c, "text", "") for c in (resultado.content or []) if getattr(c, "text", ""))[:MAX_TEXTO]


async def _responder(pregunta: str, corr: str, llm: LLM) -> dict:
    usadas: list[dict] = []
    async with AsyncExitStack() as pila:
        sesiones, tools = {}, []
        for m in MODULOS:
            try:
                r, w = await pila.enter_async_context(sse_client(url_mcp(m), timeout=10))
                s = await pila.enter_async_context(ClientSession(r, w))
                await s.initialize()
                sesiones[m] = s
                for t in (await s.list_tools()).tools:
                    tools.append({"type": "function", "function": {
                        "name": f"{m}{SEP}{t.name}", "description": f"[{m}] {t.description or ''}",
                        "parameters": t.inputSchema or {"type": "object", "properties": {}}}})
            except Exception as ex:  # noqa: BLE001
                traza("llm_error", corr=corr, agente="agente-unico", error=f"MCP {m}: {ex}"[:200])

        async def llamar(nombre: str, args: dict) -> str:
            m, _, herr = nombre.partition(SEP)
            t = time.perf_counter()
            ok = True
            try:
                res = await sesiones[m].call_tool(herr, args or {})
                ok, txt = not res.isError, _texto(res)
            except Exception as ex:  # noqa: BLE001
                ok, txt = False, f"error: {ex}"
            ms = round((time.perf_counter() - t) * 1000)
            usadas.append({"modulo": m, "herramienta": herr, "args": args or {}, "ok": ok, "ms": ms})
            traza("herramienta_mcp", corr=corr, agente="agente-unico", herramienta=f"{m}/{herr}", ok=ok, ms=ms)
            return txt

        mensajes = [{"role": "system", "content": PERFIL}, {"role": "user", "content": pregunta}]
        texto, modelo = "", None
        for _ in range(MAX_PASOS):
            msg = llm.chat(mensajes, tools)
            modelo = msg.get("_modelo")
            llamadas = msg.get("tool_calls") or []
            if not llamadas:
                texto = (msg.get("content") or "").strip()
                break
            mensajes.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": llamadas})
            for tc in llamadas:
                fn = tc["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                mensajes.append({"role": "tool", "tool_call_id": tc["id"], "content": await llamar(fn["name"], args)})
    return {"texto": texto, "modelo": modelo, "usadas": usadas}


class AgenteUnico:
    """Misma interfaz que Orquestador.preguntar(), para que el evaluador lo califique igual."""

    def __init__(self):
        self.llm = LLM()

    def preguntar(self, pregunta: str, origen: str = "cli", **_) -> dict:
        corr = nuevo_id()
        t0 = time.perf_counter()
        traza("pregunta", corr=corr, agente="agente-unico", origen=origen, pregunta=pregunta[:300], modelo=self.llm.modelo)
        try:
            r = asyncio.run(_responder(pregunta, corr, self.llm))
        except Exception as ex:  # noqa: BLE001
            traza("llm_error", corr=corr, agente="agente-unico", error=str(ex)[:200])
            r = {"texto": "", "modelo": None, "usadas": []}
        total = round((time.perf_counter() - t0) * 1000)
        consultados = [m for m in MODULOS if any(u["modulo"] == m for u in r["usadas"])]
        # Un "informe" por módulo consultado, con la respuesta única como texto (así se califica igual que B y C)
        informes = [{"corr": corr, "modulo": m, "agente": "agente-unico", "severidad": "desconocida",
                     "resumen": r["texto"], "modo": "llm+mcp" if r["texto"] else "error", "modelo": r["modelo"],
                     "herramientas": [u for u in r["usadas"] if u["modulo"] == m], "ts": ahora()} for m in consultados]
        traza("respuesta", corr=corr, agente="agente-unico", ms_total=total, modulos=len(consultados),
              herramientas=len(r["usadas"]), ok=bool(r["texto"]))
        return {"corr": corr, "pregunta": pregunta, "plan": {m: pregunta for m in consultados}, "interprete": "agente-unico",
                "informes": informes, "sin_respuesta": [],
                "veredicto": {"severidad": None, "respuesta": r["texto"], "modo": "llm", "modelo": r["modelo"]},
                "ms_total": total, "ts": ahora()}


if __name__ == "__main__":
    res = AgenteUnico().preguntar(" ".join(sys.argv[1:]) or "¿Cómo está la planta ahora?")
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
