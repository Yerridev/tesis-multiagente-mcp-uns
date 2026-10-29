"""
Agentes LLM: bucle de herramientas (razonar -> llamar herramienta MCP -> observar) y agente de equipo.
Todos los agentes comparten las mismas reglas de contexto y el mismo formato final (bloque json),
que es lo que el experimento puntua.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .llm import ClienteLLM, Uso
from .mcp_pool import PoolMCP

CONTEXTO = """Eres un agente de supervision de SOLO LECTURA del Laboratorio de Automatizacion y Simulacion de Procesos de la USS (modulos didacticos con PLC).
- Las preguntas se refieren a momentos PASADOS con fecha y hora de Lima. Para un instante usa la herramienta de diagnostico del equipo con el parametro 'momento', o consultar_historial con 'inicio' y 'fin' alrededor de ese instante. No uses lecturas en vivo (obtener_lectura, obtener_estado_plc) salvo que la pregunta diga 'ahora'.
- Nunca inventes valores: toda cifra de tu respuesta debe salir de una herramienta. Si no hay datos, dilo.
- No puedes cambiar nada en los equipos.
- Responde en espanol y breve: primero la conclusion con su numero y unidad, luego la evidencia."""

FORMATO = """Al final agrega SIEMPRE este bloque (es obligatorio):
```json
{"equipos": [{"equipo": "<id del equipo, p. ej. presion-mcp09>", "momento": "<fecha y hora ISO consultada>", "diagnostico": "<codigo exacto que devolvio la herramienta de diagnostico, o null si no la usaste>", "valores": {"<variable tal como la nombra la herramienta, p. ej. presion/psi>": <numero>}}], "respuesta": "<una linea>"}
```"""


@dataclass
class Traza:
    uso: Uso = field(default_factory=Uso)
    herramientas: list = field(default_factory=list)
    pasos: list = field(default_factory=list)

    def herramienta(self, agente: str, nombre: str, entrada: dict, texto: str, error: bool, ms: int) -> None:
        self.herramientas.append({"agente": agente, "nombre": nombre, "entrada": entrada, "error": error, "ms": ms,
                                  "texto": texto[:20000]})

    def paso(self, agente: str, tipo: str, detalle: Any = None) -> None:
        self.pasos.append({"agente": agente, "tipo": tipo, "detalle": detalle})

    def evidencia(self, limite: int = 16000, por_llamada: int = 2500) -> str:
        """Salidas reales de las herramientas, compactadas, para el verificador."""
        partes = []
        for h in self.herramientas:
            t = h["texto"]
            try:
                t = json.dumps(json.loads(t), ensure_ascii=False, separators=(",", ":"))
            except (json.JSONDecodeError, TypeError):
                pass
            partes.append(f"[{h['nombre']} {json.dumps(h['entrada'], ensure_ascii=False)}] {t[:por_llamada]}")
        return "\n".join(partes)[:limite]


def extraer_json(texto: str) -> dict | None:
    """Ultimo bloque ```json ...``` del texto; si no hay, el ultimo objeto {...} que se pueda leer."""
    if not texto:
        return None
    bloques = re.findall(r"```json\s*(\{.*?\})\s*```", texto, flags=re.S)
    candidatos = bloques[::-1] or [m.group(0) for m in re.finditer(r"\{.*\}", texto, flags=re.S)][::-1]
    for c in candidatos:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


def _mensaje_asistente(m: Any) -> dict:
    llamadas = m.tool_calls or []
    d: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
    if llamadas:
        d["tool_calls"] = [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                           for c in llamadas]
    return d


async def bucle_herramientas(llm: ClienteLLM, pool: PoolMCP, traza: Traza, agente: str, sistema: str,
                             tarea: str, herramientas: list[dict], max_rondas: int) -> str:
    """Bucle de razonamiento y accion con herramientas MCP. Devuelve el texto final del agente."""
    msgs: list[dict] = [{"role": "system", "content": sistema}, {"role": "user", "content": tarea}]
    for _ in range(max_rondas):
        m = await llm.chat(msgs, traza.uso, agente, herramientas)
        msgs.append(_mensaje_asistente(m))
        llamadas = m.tool_calls or []
        if not llamadas:
            return m.content or ""
        for c in llamadas:
            try:
                entrada = json.loads(c.function.arguments or "{}") or {}
            except json.JSONDecodeError:
                entrada = {}
            entrada = {k: v for k, v in entrada.items() if v is not None}
            texto, error, ms = await pool.llamar(c.function.name, entrada)
            traza.herramienta(agente, c.function.name, entrada, texto, error, ms)
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": texto[:30000]})
    traza.paso(agente, "tope_rondas", max_rondas)
    msgs.append({"role": "user", "content": "Se agoto el numero de consultas. Responde ya con lo que tienes, "
                                            "incluido el bloque json final."})
    m = await llm.chat(msgs, traza.uso, agente)
    return m.content or ""


def sistema_equipo(pool: PoolMCP, alias: str) -> str:
    e = pool.por_alias[alias]
    return (f"{CONTEXTO}\n\nEres el agente del equipo {e['nombre']} {e['codigo']} (id {e['id']}, PLC {e['plc']}). "
            f"Solo tienes las herramientas de este equipo; si te preguntan por otro equipo, dilo.\n\n"
            f"### Instrucciones del servidor MCP del equipo\n{pool.instrucciones[alias]}\n\n{FORMATO}")


def sistema_unico(pool: PoolMCP) -> str:
    lista = "\n".join(f"- {e['nombre']} {e['codigo']} (id {e['id']}, herramientas '{a}__'): PLC {e['plc']}"
                      for a, e in pool.por_alias.items())
    instr = "\n\n".join(f"### {pool.por_alias[a]['nombre']} (herramientas '{a}__')\n{pool.instrucciones[a]}"
                        for a in pool.por_alias)
    return (f"{CONTEXTO}\n\nEquipos integrados (cada herramienta lleva el prefijo de su equipo; nunca mezcles datos "
            f"de un equipo con otro):\n{lista}\n\n{instr}\n\n{FORMATO}")


async def agente_equipo(llm: ClienteLLM, pool: PoolMCP, traza: Traza, alias: str, tarea: str,
                        max_rondas: int = 6) -> str:
    nombre = f"agente_{alias}"
    traza.paso(nombre, "inicio", tarea)
    texto = await bucle_herramientas(llm, pool, traza, nombre, sistema_equipo(pool, alias), tarea,
                                     pool.herramientas(alias, llm.esquema_gemini), max_rondas)
    traza.paso(nombre, "fin", texto[-600:])
    return texto
