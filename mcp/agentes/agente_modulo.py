#!/usr/bin/env python3
"""
Agente ANALISTA de un módulo (uno por módulo, como Köhle et al. 2026).

Estructura del agente (Wang et al. 2024):
  perfil        → rol de analista del módulo X, solo lectura
  memoria       → evidencia determinista + resultados de herramientas de esta tarea
  planificación → el LLM decide qué herramientas MCP usar (máx. N pasos)
  acción        → cliente MCP contra SU servidor (server_modulo.py --modulo X)

La evidencia determinista va primero (diagnostico del servidor MCP): la IA la interpreta,
no la reemplaza (Ahmadi et al. 2026). Sin LLM disponible, responde solo con reglas.

Servicio:  python mcp/agentes/agente_modulo.py --modulo caudal
           escucha  {UNS}/agentes/caudal/solicitud   y publica  {UNS}/agentes/caudal/informe
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.sse import sse_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import LLM, MODULOS, TOPICO, ahora, cliente_mqtt, conectar, traza, url_mcp  # noqa: E402

MAX_PASOS = 5
MAX_TEXTO = 7000


def _perfil(modulo: str) -> str:
    c = MODULOS[modulo]
    return (
        f"Eres el agente ANALISTA del módulo de {modulo.upper()} ({c['codigo']}, PLC {c['plc']}) del "
        "Laboratorio de Automatización de la USS. Solo LEES datos con tus herramientas MCP: no puedes "
        "dar órdenes al PLC. Ya tienes la evidencia determinista (diagnostico). Usa otras herramientas "
        "solo si hacen falta para responder la subtarea. Reglas: no inventes valores; si un dato no "
        "existe dilo; distingue hechos (valores leídos) de hipótesis; respeta las señales marcadas como "
        "hipotesis. TIEMPO: diagnostico y estado_actual son el estado de AHORA. Si la subtarea pregunta por un momento "
        "pasado o por algo dicho antes, usa historial_alarmas / historial_senal (hora de Lima) y responde con horas: "
        "\"a las X estaba …, desde las Y está …\". Un cambio posterior NO invalida lo que era cierto antes: no lo "
        "presentes como corrección. Responde en español, breve (máx. 8 líneas), citando los valores que usaste."
    )


def _texto(resultado) -> str:
    partes = [getattr(c, "text", "") for c in (resultado.content or [])]
    return "\n".join(p for p in partes if p)[:MAX_TEXTO]


def _herramientas_openai(lista) -> list[dict]:
    return [{"type": "function", "function": {
        "name": t.name, "description": t.description or "",
        "parameters": t.inputSchema or {"type": "object", "properties": {}}}} for t in lista.tools]


async def analizar(modulo: str, subtarea: str, corr: str, llm: LLM | None = None) -> dict:
    """Ejecuta la subtarea sobre el módulo y devuelve un informe estructurado."""
    llm = llm or LLM()
    t0 = time.perf_counter()
    usadas: list[dict] = []

    async with sse_client(url_mcp(modulo), timeout=10) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        lista = await s.list_tools()

        async def llamar(nombre: str, args: dict | None = None) -> str:
            t = time.perf_counter()
            ok = True
            try:
                res = await s.call_tool(nombre, args or {})
                ok = not res.isError
                txt = _texto(res)
            except Exception as ex:  # noqa: BLE001
                ok, txt = False, f"error: {ex}"
            ms = round((time.perf_counter() - t) * 1000)
            usadas.append({"herramienta": nombre, "args": args or {}, "ok": ok, "ms": ms})
            traza("herramienta_mcp", corr=corr, agente=f"analista-{modulo}", herramienta=nombre, ok=ok, ms=ms)
            return txt

        # 1) evidencia determinista (siempre)
        evidencia = await llamar("diagnostico")
        try:
            diag = json.loads(evidencia)
        except json.JSONDecodeError:
            diag = {"severidad": "desconocida"}

        resumen, modo, modelo = None, "reglas", None
        if llm.disponible:
            mensajes = [{"role": "system", "content": _perfil(modulo)},
                        {"role": "user", "content": f"Subtarea: {subtarea}\n\nEvidencia determinista (diagnostico):\n{evidencia}"}]
            tools = _herramientas_openai(lista)
            try:
                for _ in range(MAX_PASOS):
                    msg = llm.chat(mensajes, tools)
                    modelo = msg.get("_modelo")
                    llamadas = msg.get("tool_calls") or []
                    if not llamadas:
                        resumen = (msg.get("content") or "").strip()
                        break
                    mensajes.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": llamadas})
                    for tc in llamadas:
                        fn = tc["function"]
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        mensajes.append({"role": "tool", "tool_call_id": tc["id"], "content": await llamar(fn["name"], args)})
                modo = "llm+mcp"
            except Exception as ex:  # noqa: BLE001  el modelo no soporta herramientas o falló
                traza("llm_error", corr=corr, agente=f"analista-{modulo}", error=str(ex)[:200])
                try:  # segundo intento sin herramientas: solo interpreta la evidencia + estado
                    estado = await llamar("estado_actual")
                    msg = llm.chat([{"role": "system", "content": _perfil(modulo)},
                                    {"role": "user", "content": f"Subtarea: {subtarea}\n\nDiagnostico:\n{evidencia}\n\nEstado:\n{estado}"}])
                    resumen, modo, modelo = (msg.get("content") or "").strip(), "llm", msg.get("_modelo")
                except Exception as ex2:  # noqa: BLE001
                    traza("llm_error", corr=corr, agente=f"analista-{modulo}", error=str(ex2)[:200])

        if not resumen:  # sin IA: informe solo con reglas
            hall = "; ".join(h["hallazgo"] for h in diag.get("hallazgos", [])) or "sin hallazgos"
            resumen = (f"[reglas] {modulo}: severidad {diag.get('severidad')}, selector {diag.get('selector')}, "
                       f"en marcha {diag.get('en_marcha')}, valor {diag.get('valor')} (consigna {diag.get('consigna')}). "
                       f"Hallazgos: {hall}.")
            modo = "reglas"

    informe = {
        "corr": corr, "modulo": modulo, "agente": f"analista-{modulo}", "subtarea": subtarea,
        "severidad": diag.get("severidad", "desconocida"),   # la severidad SIEMPRE sale de las reglas
        "hallazgos": diag.get("hallazgos", []), "resumen": resumen, "modo": modo, "modelo": modelo,
        "herramientas": usadas, "ms": round((time.perf_counter() - t0) * 1000), "ts": ahora(),
    }
    traza("informe_modulo", corr=corr, agente=informe["agente"], severidad=informe["severidad"],
          modo=modo, modelo=modelo, ms=informe["ms"], herramientas=len(usadas))
    return informe


def servicio(modulo: str) -> None:
    """Agente como servicio: atiende solicitudes por MQTT (coordinación entre agentes)."""
    llm = LLM()
    cola: asyncio.Queue = asyncio.Queue()
    bucle = asyncio.new_event_loop()
    t_sol, t_inf = f"{TOPICO}/{modulo}/solicitud", f"{TOPICO}/{modulo}/informe"
    cli = cliente_mqtt(f"analista-{modulo}")

    def on_message(_c, _u, m):
        try:
            bucle.call_soon_threadsafe(cola.put_nowait, json.loads(m.payload))
        except Exception:  # noqa: BLE001
            pass

    cli.on_message = on_message
    conectar(cli, lambda c: c.subscribe(t_sol, qos=1))
    print(f"[analista-{modulo}] escuchando {t_sol} · MCP {url_mcp(modulo)} · LLM {llm.modelo if llm.disponible else 'NO (solo reglas)'}", flush=True)

    async def atender():
        while True:
            sol = await cola.get()
            corr = sol.get("corr", "?")
            print(f"[analista-{modulo}] {corr}: {sol.get('subtarea', '')[:80]}", flush=True)
            try:
                llm_sol = LLM(sol["modelo"]) if sol.get("modelo") else llm
                inf = await analizar(modulo, sol.get("subtarea", "Estado general del módulo"), corr, llm_sol)
            except Exception as ex:  # noqa: BLE001  p. ej. el servidor MCP no responde
                inf = {"corr": corr, "modulo": modulo, "agente": f"analista-{modulo}", "severidad": "desconocida",
                       "resumen": f"No pude consultar mi servidor MCP: {ex}", "modo": "error", "hallazgos": [],
                       "herramientas": [], "ms": 0, "ts": ahora()}
                traza("informe_modulo", corr=corr, agente=inf["agente"], severidad="desconocida", modo="error", error=str(ex)[:200])
            cli.publish(t_inf, json.dumps(inf, ensure_ascii=False, default=str), qos=1)

    bucle.run_until_complete(atender())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modulo", required=True, choices=list(MODULOS))
    ap.add_argument("--una-vez", metavar="SUBTAREA", help="analiza una vez e imprime el informe (sin MQTT)")
    a = ap.parse_args()
    if a.una_vez:
        print(json.dumps(asyncio.run(analizar(a.modulo, a.una_vez, "manual")), ensure_ascii=False, indent=2, default=str))
    else:
        servicio(a.modulo)
