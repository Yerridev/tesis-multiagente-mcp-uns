"""
Las tres configuraciones del experimento (misma pregunta, mismo modelo, mismos servidores MCP):

  A  Agente unico (linea base): un LLM con las herramientas de TODOS los equipos (bucle de hasta 10 rondas).
  B  Multiagente centralizado: un coordinador LLM planifica que agentes de equipo consultar, los ejecuta en
     paralelo, sintetiza y un verificador LLM contrasta las cifras con las salidas de las herramientas.
  C  Hibrido: enrutamiento por reglas (workflow, sin LLM). Si la pregunta nombra un solo equipo, responde su
     agente directamente; si nombra varios (o ninguno), los agentes trabajan en paralelo y el coordinador
     sintetiza. Tambien pasa por el verificador.

El verificador se puede desactivar (verificar=False) para medir su efecto (ablacion).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import unicodedata

from .agentes import (CONTEXTO, FORMATO, Traza, agente_equipo, bucle_herramientas, extraer_json,
                      sistema_unico)
from .llm import ClienteLLM
from .mcp_pool import PoolMCP

# Palabras con las que el enrutador por reglas reconoce cada equipo (sin tildes, en minusculas)
PALABRAS = {
    "caudal": ["caudal", "mcc-09", "mcc09", "l/min", "s7-200"],
    "nivel": ["nivel del tanque", "modulo de nivel", "nivel mcn", "mcn-09", "mcn09", "micrologix"],
    "presion": ["presion", "mcp-09", "mcp09", "psi", "cfp"],
    "temperatura": ["temperatura", "mct-09", "mct09", "twido", "calentamiento"],
}


def _normal(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def enrutar(pregunta: str, disponibles: list[str]) -> list[str]:
    """Enrutador por reglas de la configuracion C. Ninguna coincidencia -> todos los equipos."""
    q = _normal(pregunta)
    elegidos = [a for a in disponibles if any(p in q for p in PALABRAS.get(a, [a]))]
    return elegidos or list(disponibles)


def _lista_equipos(pool: PoolMCP) -> str:
    return "\n".join(f"- {e['id']} (alias {a}): {e['nombre']} {e['codigo']}, proceso {e['proceso']}, PLC {e['plc']}"
                     for a, e in pool.por_alias.items())


async def _planificar(llm: ClienteLLM, pool: PoolMCP, traza: Traza, pregunta: str) -> list[dict]:
    """Coordinador de B: decide que agentes de equipo consultar y con que tarea (JSON)."""
    sistema = (f"Eres el COORDINADOR de un sistema multiagente de supervision de solo lectura. No tienes "
               f"herramientas: delegas en agentes de equipo, cada uno con acceso solo a su equipo.\n"
               f"Equipos:\n{_lista_equipos(pool)}\n\n"
               f"Devuelve SOLO un JSON: {{\"subtareas\": [{{\"equipo\": \"<alias>\", \"tarea\": \"<instruccion "
               f"autocontenida para ese agente, con la fecha y hora exactas y lo que debe averiguar>\"}}]}}.\n"
               f"Reglas: una subtarea por equipo involucrado; si la pregunta trata de un solo equipo, una sola "
               f"subtarea; copia literalmente las fechas y horas de la pregunta.")
    m = await llm.chat([{"role": "system", "content": sistema}, {"role": "user", "content": pregunta}],
                       traza.uso, "coordinador")
    plan = extraer_json(m.content or "") or {}
    subtareas = [s for s in plan.get("subtareas", []) if isinstance(s, dict) and s.get("equipo") in pool.por_alias]
    traza.paso("coordinador", "plan", subtareas or m.content)
    if not subtareas:  # plan ilegible: consultar a todos con la pregunta original
        subtareas = [{"equipo": a, "tarea": pregunta} for a in pool.por_alias]
    return subtareas


async def _sintetizar(llm: ClienteLLM, traza: Traza, pregunta: str, informes: dict[str, str]) -> str:
    sistema = (f"{CONTEXTO}\n\nEres el COORDINADOR: integra los informes de los agentes de equipo para responder "
               f"la pregunta del usuario. No agregues cifras que no esten en los informes. Une en tu bloque json "
               f"final las entradas 'equipos' de todos los informes.\n\n{FORMATO}")
    cuerpo = "\n\n".join(f"### Informe del agente {a}\n{t}" for a, t in informes.items())
    m = await llm.chat([{"role": "system", "content": sistema},
                        {"role": "user", "content": f"PREGUNTA: {pregunta}\n\n{cuerpo}"}], traza.uso, "coordinador")
    return m.content or ""


async def _verificar(llm: ClienteLLM, traza: Traza, pregunta: str, borrador: str) -> str:
    """Verificador (evaluador-optimizador): contrasta cifras y diagnosticos del borrador con la evidencia;
    si encuentra problemas, pide UNA correccion."""
    evidencia = traza.evidencia()
    sistema = ("Eres un VERIFICADOR. Compara cada cifra y cada codigo de diagnostico del BORRADOR con la EVIDENCIA "
               "(salidas reales de las herramientas). Responde SOLO un JSON: {\"ok\": true|false, \"problemas\": "
               "[\"...\"]}. Es problema: una cifra que no aparece en la evidencia (admite redondeo), un diagnostico "
               "distinto del devuelto por la herramienta, datos de un equipo atribuidos a otro, o que falte el "
               "bloque json final.")
    m = await llm.chat([{"role": "system", "content": sistema},
                        {"role": "user", "content": f"PREGUNTA: {pregunta}\n\nBORRADOR:\n{borrador}\n\n"
                                                    f"EVIDENCIA:\n{evidencia}"}], traza.uso, "verificador")
    veredicto = extraer_json(m.content or "") or {"ok": True, "problemas": ["veredicto ilegible"]}
    traza.paso("verificador", "veredicto", veredicto)
    if veredicto.get("ok", True) or not veredicto.get("problemas"):
        return borrador
    sistema_c = (f"{CONTEXTO}\n\nCorrige el BORRADOR usando SOLO la EVIDENCIA. Mantén lo que esta bien.\n\n{FORMATO}")
    m = await llm.chat([{"role": "system", "content": sistema_c},
                        {"role": "user", "content": f"PREGUNTA: {pregunta}\n\nBORRADOR:\n{borrador}\n\n"
                                                    f"PROBLEMAS:\n- " + "\n- ".join(map(str, veredicto["problemas"]))
                                                    + f"\n\nEVIDENCIA:\n{evidencia}"}], traza.uso, "verificador")
    traza.paso("verificador", "correccion", True)
    return m.content or borrador


async def responder(config: str, pregunta: str, llm: ClienteLLM, pool: PoolMCP, verificar: bool = True) -> dict:
    """Responde una pregunta con la configuracion A, B o C. Devuelve respuesta, ruta seguida y traza."""
    traza = Traza()
    t0 = time.perf_counter()
    ruta: list[str] = []
    if config == "A":
        todas = [h for a in pool.por_alias for h in pool.herramientas(a, llm.esquema_gemini)]
        texto = await bucle_herramientas(llm, pool, traza, "agente_unico", sistema_unico(pool), pregunta, todas, 10)
        ruta = ["agente_unico"]
    elif config == "B":
        subtareas = await _planificar(llm, pool, traza, pregunta)
        informes_l = await asyncio.gather(*(agente_equipo(llm, pool, traza, s["equipo"], s["tarea"])
                                            for s in subtareas))
        informes = {s["equipo"]: t for s, t in zip(subtareas, informes_l)}
        texto = await _sintetizar(llm, traza, pregunta, informes)
        ruta = ["coordinador"] + [f"agente_{a}" for a in informes] + ["sintesis"]
        if verificar:
            texto = await _verificar(llm, traza, pregunta, texto)
            ruta.append("verificador")
    elif config == "C":
        elegidos = enrutar(pregunta, list(pool.por_alias))
        traza.paso("enrutador", "reglas", elegidos)
        if len(elegidos) == 1:
            texto = await agente_equipo(llm, pool, traza, elegidos[0], pregunta)
            ruta = [f"agente_{elegidos[0]}"]
        else:
            tareas = {a: f"{pregunta}\n\n(Responde solo sobre tu equipo; otros agentes cubren los demas.)"
                      for a in elegidos}
            informes_l = await asyncio.gather(*(agente_equipo(llm, pool, traza, a, t) for a, t in tareas.items()))
            texto = await _sintetizar(llm, traza, pregunta, dict(zip(elegidos, informes_l)))
            ruta = [f"agente_{a}" for a in elegidos] + ["sintesis"]
        if verificar:
            texto = await _verificar(llm, traza, pregunta, texto)
            ruta.append("verificador")
    else:
        raise ValueError(f"configuracion desconocida: {config}")
    return {"respuesta": texto, "json": extraer_json(texto), "ruta": ruta,
            "latencia_s": round(time.perf_counter() - t0, 2), "uso": traza.uso.resumen(),
            "llamadas_herramientas": len(traza.herramientas),
            "herramientas_con_error": sum(h["error"] for h in traza.herramientas),
            "traza": {"pasos": traza.pasos, "herramientas": traza.herramientas}}
