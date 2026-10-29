"""
Pool de servidores MCP reales (stdio), uno por equipo del registro equipos.json.
Es el mismo mecanismo que usa el lienzo: los agentes llaman a las herramientas por el protocolo MCP,
no importando funciones de Python, para que el experimento mida la arquitectura verdadera.
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent          # historiador/
MCP_DIR = RAIZ / "mcp_servidor"
REGISTRO = MCP_DIR / "conocimiento" / "equipos.json"

_CLAVES_ESQUEMA = {"type", "description", "properties", "items", "enum", "required", "format"}


def esquema_compatible(x: Any) -> Any:
    """Gemini acepta un subconjunto de JSON Schema (igual que en el lienzo): sin title/default/additionalProperties
    y anyOf [X, null] -> X nullable."""
    if isinstance(x, list):
        return [esquema_compatible(v) for v in x]
    if not isinstance(x, dict):
        return x
    if "anyOf" in x:
        opciones = [o for o in x["anyOf"] if o.get("type") != "null"]
        base = dict(opciones[0]) if opciones else {"type": "string"}
        if "description" in x:
            base.setdefault("description", x["description"])
        out = esquema_compatible(base)
        if len(opciones) < len(x["anyOf"]):
            out["nullable"] = True
        return out
    out = {}
    for k, v in x.items():
        if k == "properties":
            out[k] = {pk: esquema_compatible(pv) for pk, pv in v.items()}
        elif k in _CLAVES_ESQUEMA:
            out[k] = esquema_compatible(v)
    if out.get("type") == "object" and "properties" not in out:
        out["properties"] = {}
    return out


def leer_registro() -> list[dict]:
    return json.loads(REGISTRO.read_text(encoding="utf-8"))["equipos"]


class PoolMCP:
    """async with PoolMCP(dsn) as pool: pool.herramientas('presion'), await pool.llamar('presion__obtener_lectura', {...})"""

    def __init__(self, dsn: str, equipos: list[str] | None = None):
        self.dsn = dsn
        self.equipos = [e for e in leer_registro() if not equipos or e["alias"] in equipos or e["id"] in equipos]
        self.por_alias = {e["alias"]: e for e in self.equipos}
        self.sesiones: dict[str, Any] = {}
        self.tools: dict[str, list] = {}
        self.instrucciones: dict[str, str] = {}
        self._pila = AsyncExitStack()

    async def __aenter__(self) -> "PoolMCP":
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        for e in self.equipos:
            params = StdioServerParameters(command=sys.executable, args=[str(MCP_DIR / e["mcp_script"])],
                                           env={**os.environ, "MCP_DSN": self.dsn})
            r, w = await self._pila.enter_async_context(stdio_client(params))
            s = await self._pila.enter_async_context(ClientSession(r, w))
            init = await s.initialize()
            self.sesiones[e["alias"]] = s
            self.tools[e["alias"]] = (await s.list_tools()).tools
            self.instrucciones[e["alias"]] = init.instructions or ""
        return self

    async def __aexit__(self, *exc) -> None:
        await self._pila.aclose()

    def herramientas(self, alias: str, esquema_gemini: bool) -> list[dict]:
        """Herramientas de UN equipo en formato OpenAI, con nombre 'alias__herramienta'."""
        e = self.por_alias[alias]
        out = []
        for t in self.tools[alias]:
            params = esquema_compatible(t.input_schema) if esquema_gemini else t.input_schema
            out.append({"type": "function", "function": {
                "name": f"{alias}__{t.name}",
                "description": f"[{e['nombre']} {e['codigo']}] {t.description or ''}"[:1000],
                "parameters": params}})
        return out

    async def llamar(self, nombre: str, entrada: dict) -> tuple[str, bool, int]:
        """Ejecuta 'alias__herramienta'. Devuelve (texto, es_error, ms)."""
        alias, _, herramienta = nombre.partition("__")
        if alias not in self.sesiones or not herramienta:
            return f"Herramienta desconocida: {nombre}", True, 0
        t0 = time.perf_counter()
        try:
            res = await self.sesiones[alias].call_tool(herramienta, entrada)
            texto = "".join(getattr(c, "text", "") for c in res.content)
            return texto, bool(res.is_error), round((time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            return f"Error al llamar {nombre}: {e}", True, round((time.perf_counter() - t0) * 1000)
