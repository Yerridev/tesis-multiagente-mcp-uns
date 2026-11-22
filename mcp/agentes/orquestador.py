#!/usr/bin/env python3
"""
ORQUESTADOR del sistema multiagente (arquitectura con orquestador, Köhle et al. 2026).

Dos roles en secuencia (Guo et al. 2024: roles distintos + comunicación + coordinación):
  1. INTÉRPRETE  entiende la pregunta y decide qué módulos consultar y qué subtarea darle a cada uno.
  2. (los ANALISTAS de cada módulo trabajan en paralelo y responden por MQTT)
  3. VEREDICTO   integra los informes, revisa que sean consistentes y emite la respuesta final.
     La severidad global es determinista (la peor de los módulos); la IA solo redacta y relaciona.

Uso:
  python mcp/agentes/orquestador.py "¿cómo está la planta?"      (una pregunta, imprime la respuesta)
  python mcp/agentes/orquestador.py --servicio                    (atiende {UNS}/agentes/orquestador/solicitud)
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import LLM, MODULOS, TOPICO, ahora, cliente_mqtt, conectar, extraer_json, nuevo_id, traza, url_mcp  # noqa: E402

ESPERA_S = 120
ORDEN_SEV = {"normal": 0, "desconocida": 1, "advertencia": 2, "alarma": 3}

PALABRAS = {
    "nivel": ["nivel", "mcn", "ultrason", "micrologix", "tanque 2", "t2 de nivel"],
    "caudal": ["caudal", "mcc", "kobold", "s7", "siemens", "l/min", "guardamotor"],
    "presion": ["presion", "presión", "mcp-09", "psi", "fieldpoint", "cfp"],
    "temperatura": ["temperatura", "mct", "twido", "°c", "resistencia", "enfriador", "calent"],
}

INTERPRETE = (
    "Eres el agente INTÉRPRETE de un sistema multiagente industrial con 4 módulos: nivel, caudal, presion, "
    "temperatura. Recibes la pregunta de un operador y decides qué módulos deben analizarla y qué subtarea "
    "concreta darle a cada analista. Si la pregunta es general (estado de la planta) usa los 4. "
    'Responde SOLO un JSON: {"modulos": {"<modulo>": "<subtarea>"}, "intencion": "<una línea>"}'
)

VEREDICTO = (
    "Eres el agente VEREDICTO de un sistema multiagente industrial (solo lectura, no das órdenes al PLC). "
    "Recibes la pregunta del operador y los informes de los agentes analistas de cada módulo. Integra los "
    "informes, señala relaciones o contradicciones entre ellos, y responde al operador en español, claro y "
    "breve (máx. 10 líneas). No inventes datos que no estén en los informes. La severidad global ya está "
    "calculada por reglas: no la cambies. Termina con una recomendación concreta si hay alarma o advertencia."
)


def _contexto(historial: list | None) -> str:
    """Últimos turnos del chat para entender preguntas cortas ("¿y el de caudal?")."""
    if not historial:
        return ""
    lineas = [f"{(h.get('rol') or '?')}: {(h.get('texto') or '')[:300]}" for h in historial[-6:]]
    return "Conversación previa:\n" + "\n".join(lineas) + "\n\nPregunta actual: "


def interpretar(pregunta: str, llm: LLM, corr: str, historial: list | None = None, solo_reglas: bool = False) -> tuple[dict, str]:
    """Rol INTÉRPRETE: pregunta → {modulo: subtarea}. solo_reglas=True es la configuración C (enrutador por reglas, sin IA)."""
    t = time.perf_counter()
    plan, modo = None, "reglas"
    if llm.disponible and not solo_reglas:
        try:
            msg = llm.chat([{"role": "system", "content": INTERPRETE}, {"role": "user", "content": _contexto(historial) + pregunta}])
            j = extraer_json(msg.get("content") or "") or {}
            mods = {m: str(s) for m, s in (j.get("modulos") or {}).items() if m in MODULOS}
            if mods:
                plan, modo = mods, "llm"
        except Exception as ex:  # noqa: BLE001
            traza("llm_error", corr=corr, agente="interprete", error=str(ex)[:200])
    if not plan:  # reglas: por palabras clave; si no menciona ninguno, los 4
        p = pregunta.lower()
        elegidos = [m for m, ps in PALABRAS.items() if any(x in p for x in ps)] or list(MODULOS)
        plan = {m: pregunta for m in elegidos}
    traza("interpretacion", corr=corr, agente="interprete", modo=modo, modulos=list(plan),
          ms=round((time.perf_counter() - t) * 1000))
    return plan, modo


def veredicto(pregunta: str, informes: list[dict], faltan: list[str], llm: LLM, corr: str, historial: list | None = None) -> dict:
    """Rol VEREDICTO: integra los informes. Severidad global = la peor (determinista)."""
    t = time.perf_counter()
    sev = max((i.get("severidad", "desconocida") for i in informes), key=lambda s: ORDEN_SEV.get(s, 1), default="desconocida")
    if faltan:
        sev = max([sev, "desconocida"], key=lambda s: ORDEN_SEV.get(s, 1))
    texto, modo, modelo = None, "reglas", None
    if llm.disponible and informes:
        resumen = [{k: i.get(k) for k in ("modulo", "severidad", "resumen", "hallazgos")} for i in informes]
        try:
            msg = llm.chat([{"role": "system", "content": VEREDICTO},
                            {"role": "user", "content": json.dumps({"pregunta": _contexto(historial) + pregunta, "severidad_global": sev,
                                                                    "informes": resumen, "sin_respuesta": faltan},
                                                                   ensure_ascii=False, default=str)}])
            texto, modo, modelo = (msg.get("content") or "").strip() or None, "llm", msg.get("_modelo")
        except Exception as ex:  # noqa: BLE001
            traza("llm_error", corr=corr, agente="veredicto", error=str(ex)[:200])
    if not texto:
        lineas = [f"Severidad global: {sev.upper()}"]
        lineas += [f"- {i['modulo']}: {i.get('severidad')} · {i.get('resumen', '')[:220]}" for i in informes]
        lineas += [f"- {m}: el agente no respondió a tiempo" for m in faltan]
        texto, modo = "\n".join(lineas), "reglas"
    ms = round((time.perf_counter() - t) * 1000)
    traza("veredicto", corr=corr, agente="veredicto", severidad=sev, modo=modo, modelo=modelo, ms=ms)
    return {"severidad": sev, "respuesta": texto, "modo": modo, "modelo": modelo, "ms": ms}


class Orquestador:
    def __init__(self):
        self.llm = LLM()
        self._esperas: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.llamadas: collections.deque = collections.deque(maxlen=60)
        self.cli = cliente_mqtt("orquestador")
        self.cli.on_message = self._mensaje
        conectar(self.cli, lambda c: c.subscribe(f"{TOPICO}/+/informe", qos=1))
        time.sleep(0.5)

    def _mensaje(self, _c, _u, m):
        try:
            inf = json.loads(m.payload)
        except Exception:  # noqa: BLE001
            return
        with self._lock:
            # registro de llamadas MCP (de cualquier origen: web, bat 32, evaluador) para la página "Servidores MCP"
            for h in reversed(inf.get("herramientas", [])):
                self.llamadas.appendleft({"ts": inf.get("ts"), "agente": inf.get("agente"), "servidor": f"mcp-{inf.get('modulo')}",
                                          "herramienta": h.get("herramienta"), "ok": h.get("ok"), "ms": h.get("ms"), "corr": inf.get("corr")})
            e = self._esperas.get(inf.get("corr"))
            if e is not None and inf.get("modulo") in e["pendientes"]:
                e["informes"].append(inf)
                e["pendientes"].discard(inf["modulo"])
                if not e["pendientes"]:
                    e["listo"].set()

    def preguntar(self, pregunta: str, origen: str = "cli", historial: list | None = None, modelo: str | None = None,
                  enrutador_reglas: bool = False) -> dict:
        corr = nuevo_id()
        t0 = time.perf_counter()
        llm = LLM(modelo) if modelo else self.llm   # el chat web puede elegir el modelo
        traza("pregunta", corr=corr, agente="orquestador", origen=origen, pregunta=pregunta[:300], modelo=llm.modelo)
        plan, modo_int = interpretar(pregunta, llm, corr, historial, solo_reglas=enrutador_reglas)
        espera = {"pendientes": set(plan), "informes": [], "listo": threading.Event()}
        with self._lock:
            self._esperas[corr] = espera
        for m, sub in plan.items():  # coordinación: una solicitud por analista, en paralelo, vía MQTT
            self.cli.publish(f"{TOPICO}/{m}/solicitud", json.dumps({"corr": corr, "subtarea": sub, "modelo": modelo, "ts": ahora()},
                                                                  ensure_ascii=False), qos=1)
            traza("solicitud", corr=corr, agente="orquestador", destino=f"analista-{m}")
        espera["listo"].wait(ESPERA_S)
        with self._lock:
            self._esperas.pop(corr, None)
        faltan = sorted(espera["pendientes"])
        ver = veredicto(pregunta, espera["informes"], faltan, llm, corr, historial)
        total = round((time.perf_counter() - t0) * 1000)
        resultado = {"corr": corr, "pregunta": pregunta, "plan": plan, "interprete": modo_int,
                     "informes": espera["informes"], "sin_respuesta": faltan, "veredicto": ver,
                     "ms_total": total, "ts": ahora()}
        traza("respuesta", corr=corr, agente="orquestador", severidad=ver["severidad"], ms_total=total,
              modulos=len(plan), respondieron=len(espera["informes"]), ok=not faltan)
        return resultado

    def servicio(self):
        def on_sol(_c, _u, m):
            try:
                sol = json.loads(m.payload)
            except Exception:  # noqa: BLE001
                return
            def trabajo():
                r = self.preguntar(sol.get("pregunta", ""), sol.get("origen", "mqtt"), sol.get("historial"), sol.get("modelo"))
                r["id_solicitud"] = sol.get("id")
                self.cli.publish(f"{TOPICO}/orquestador/respuesta", json.dumps(r, ensure_ascii=False, default=str), qos=1)
            threading.Thread(target=trabajo, daemon=True).start()
        t = f"{TOPICO}/orquestador/solicitud"
        self.cli.message_callback_add(t, on_sol)
        self.cli.subscribe(t, qos=1)
        # estado retenido: el backend sabe al instante si el sistema multiagente está corriendo
        est = cliente_mqtt("orquestador-estado")
        t_est = f"{TOPICO}/orquestador/estado"
        est.will_set(t_est, json.dumps({"estado": "fuera_de_linea"}), qos=1, retain=True)
        conectar(est, lambda c: c.publish(t_est, json.dumps({"estado": "en_linea", "ts": ahora(),
                                                              "modelo": self.llm.modelo if self.llm.disponible else None}),
                                          qos=1, retain=True))
        print(f"[orquestador] escuchando {t} · LLM {self.llm.modelo if self.llm.disponible else 'NO (solo reglas)'}", flush=True)
        while True:   # catálogo retenido: servidores MCP en línea + sus herramientas + últimas llamadas
            try:
                cat = asyncio.run(catalogo_mcp())
                cat["llamadas"] = list(self.llamadas)
                est.publish(f"{TOPICO}/catalogo", json.dumps(cat, ensure_ascii=False, default=str), qos=1, retain=True)
            except Exception as ex:  # noqa: BLE001
                print(f"[orquestador] catálogo MCP: {ex}", flush=True)
            time.sleep(15)


async def catalogo_mcp() -> dict:
    """Pregunta a cada servidor MCP qué herramientas publica (list_tools): es el catálogo REAL, no una lista fija."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async def uno(modulo: str) -> dict:
        c = MODULOS[modulo]
        base = {"modulo": modulo, "servidor": f"mcp-{modulo}", "url": url_mcp(modulo), "puerto": c["puerto"],
                "plc": c["plc"], "codigo": c["codigo"]}
        t = time.perf_counter()
        try:
            async with sse_client(url_mcp(modulo), timeout=5) as (r, w), ClientSession(r, w) as s:
                await s.initialize()
                lista = await s.list_tools()
            return {**base, "en_linea": True, "ms": round((time.perf_counter() - t) * 1000),
                    "herramientas": [{"nombre": x.name, "descripcion": (x.description or "").split("\n")[0]} for x in lista.tools]}
        except Exception as ex:  # noqa: BLE001
            return {**base, "en_linea": False, "error": str(ex)[:120], "herramientas": []}

    return {"ts": ahora(), "servidores": list(await asyncio.gather(*(uno(m) for m in MODULOS)))}


def imprimir(r: dict) -> None:
    v = r["veredicto"]
    print("\n" + "=" * 70)
    print(f"PREGUNTA : {r['pregunta']}")
    print(f"PLAN     : {', '.join(r['plan'])}  (intérprete: {r['interprete']})")
    for i in r["informes"]:
        h = ", ".join(x["herramienta"] for x in i.get("herramientas", []))
        print(f"  · {i['agente']:<22} {i['severidad']:<11} {i['modo']:<8} {i['ms']:>6} ms  [{h}]")
    for m in r["sin_respuesta"]:
        print(f"  · analista-{m:<13} SIN RESPUESTA (¿está corriendo?)")
    print("-" * 70)
    print(f"VEREDICTO ({v['severidad'].upper()} · {v['modo']}{' · ' + v['modelo'] if v.get('modelo') else ''}):")
    print(v["respuesta"])
    print(f"\nTiempo total: {r['ms_total']} ms · traza: registros/agentes · corr {r['corr']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pregunta", nargs="?")
    ap.add_argument("--servicio", action="store_true")
    ap.add_argument("--json", action="store_true", help="imprime el resultado completo en JSON")
    a = ap.parse_args()
    o = Orquestador()
    if a.servicio:
        o.servicio()
    else:
        res = o.preguntar(a.pregunta or "¿Cómo está la planta ahora?")
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str)) if a.json else imprimir(res)
