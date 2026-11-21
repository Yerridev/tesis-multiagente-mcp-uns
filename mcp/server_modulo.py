#!/usr/bin/env python3
"""
Servidor MCP de UN módulo del laboratorio — SOLO LECTURA.

Cada módulo (nivel, caudal, presión, temperatura) tiene su propio servidor MCP, como en
Köhle et al. (2026): el servidor es el único que sabe de dónde salen los datos (backend /
UNS); el agente solo ve el nombre, la descripción y el esquema de cada herramienta.

NO hay herramientas de escritura: las órdenes pasan solo por el servicio determinista de
control del backend (autenticación + enclavamientos + auditoría).

Herramientas:
  estado_actual        valor principal, estado, consigna y frescura
  senales              todas las señales del PLC con su significado (catálogo)
  historial            últimas mediciones del búfer del backend
  diagnostico          evaluación determinista (comunicación, alarmas, selector, marcha)
  metadatos            PLC, protocolo, IP, tópico UNS
  grafo_conocimiento   nodos y relaciones del proceso + conocimiento del módulo
  calidad_frescura     edad del último dato

Uso:  python mcp/server_modulo.py --modulo caudal   (BACKEND_URL, SERVICIO_TOKEN)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modulos import MODULOS, UNS, conocimiento  # noqa: E402

FRESCURA_MAX_S = 30
BACKEND = os.environ.get("BACKEND_URL", "http://backend:8080").rstrip("/")
_CAB = {"Authorization": f"Bearer {os.environ['SERVICIO_TOKEN']}"} if os.environ.get("SERVICIO_TOKEN") else {}


# (clave, valor que indica alarma, texto) · mismo criterio que el SCADA
_ALARMAS_SCADA = [
    ("estado/nivel_alto", True, "NIVEL ALTO en el tanque (indicador Q0.0)"),
    ("estado/nivel_bajo", True, "NIVEL BAJO en el tanque (indicador Q0.1)"),
    ("nivel/principal_alto", True, "NIVEL ALTO en el tanque principal (bloquea el lazo)"),
    ("nivel/enfriador_alto", True, "NIVEL ALTO en el tanque del enfriador"),
    ("nivel/principal_bajo_ok", False, "Tanque principal SIN AGUA sobre el interruptor de nivel bajo"),
    ("nivel/enfriador_bajo_ok", False, "Tanque del enfriador SIN AGUA sobre el interruptor de nivel bajo"),
]


def crear_servidor(modulo: str, puerto: int | None = None) -> FastMCP:
    cfg = MODULOS[modulo]
    eq_id = cfg["equipo"]
    con = conocimiento(modulo)
    catalogo = {s["clave"]: s for s in con["senales"]}
    mcp = FastMCP(f"mcp-{modulo}", host="0.0.0.0", port=puerto or cfg["puerto"])

    def _get(path: str):
        r = httpx.get(f"{BACKEND}{path}", timeout=10.0, headers=_CAB)
        r.raise_for_status()
        return r.json()

    def _equipo() -> dict | None:
        return next((e for e in _get("/api/equipment") if e.get("id") == eq_id), None)

    def _valores() -> dict:
        try:
            datos = _get(f"/api/equipment/{eq_id}/signals") or {}
        except Exception:  # noqa: BLE001
            return {}
        return {k: (v or {}).get("valor") for k, v in (datos.get("valores") or {}).items()}

    def _edad(ts: str | None) -> float | None:
        if not ts:
            return None
        try:
            t = datetime.fromisoformat(ts)
            return round((datetime.now(t.tzinfo) - t).total_seconds(), 1)
        except ValueError:
            return None

    def _bool(valores: dict, clave: str):
        v = valores.get(clave)
        return v if isinstance(v, bool) else (bool(v) if isinstance(v, (int, float)) else None)

    @mcp.tool()
    def estado_actual() -> dict:
        """Estado en vivo del módulo: variable principal, unidad, consigna, estado ONLINE/OFFLINE y frescura."""
        eq = _equipo()
        if eq is None:
            return {"error": f"{eq_id} no disponible en el backend"}
        medible = eq.get("calidad", "buena") == "buena"
        return {
            "modulo": modulo, "equipo": eq_id, "variable": cfg["variable"],
            "valor": eq.get("value") if medible else None, "unidad": eq.get("unit"),
            "consigna": eq.get("setpoint"), "estado": eq.get("status"), "calidad": eq.get("calidad"),
            "timestamp": eq.get("timestamp"), "edad_segundos": _edad(eq.get("timestamp")),
            "solo_lectura": True,
        }

    @mcp.tool()
    def senales(filtro: str = "") -> dict:
        """Señales del PLC con su significado, unidad y dirección. `filtro` busca por texto (p. ej. 'selector', 'pid', 'nivel')."""
        valores = _valores()
        f = filtro.lower().strip()
        salida = []
        for clave in sorted(set(valores) | set(catalogo)):
            c = catalogo.get(clave, {})
            fila = {"clave": clave, "valor": valores.get(clave), "unidad": c.get("unidad", ""),
                    "significado": c.get("descripcion", "(sin descripción en el catálogo)"),
                    "direccion": c.get("direccion", ""), "hipotesis": c.get("hipotesis", False)}
            if not f or f in clave.lower() or f in fila["significado"].lower():
                salida.append(fila)
        return {"modulo": modulo, "total": len(salida), "senales": salida,
                "nota": "hipotesis=true: significado aún no confirmado en el PLC real"}

    @mcp.tool()
    def historial(limit: int = 120) -> list:
        """Últimas mediciones de la variable principal (búfer del backend, máx. 600)."""
        datos = _get(f"/api/history?equipmentId={eq_id}&limit={max(1, min(limit, 600))}")
        return datos if isinstance(datos, list) else []

    def _bd(sql: str, args: tuple) -> list:
        dsn = os.environ.get("MCP_DB_DSN")
        if not dsn:
            raise RuntimeError("sin acceso a la base de datos (MCP_DB_DSN)")
        import psycopg
        with psycopg.connect(dsn, connect_timeout=5) as c:
            c.execute("SET TRANSACTION READ ONLY")
            return c.execute(sql, args).fetchall()

    def _cambios(claves: list[str], minutos: int) -> dict:
        """Transiciones de señales en TimescaleDB (hora de Lima)."""
        minutos = max(1, min(int(minutos), 24 * 60))
        filas = _bd(
            """WITH x AS (
                 SELECT s.nombre, m.ts, m.valor,
                        lag(m.valor) OVER (PARTITION BY s.nombre ORDER BY m.ts) AS previo,
                        row_number() OVER (PARTITION BY s.nombre ORDER BY m.ts) AS n
                   FROM mediciones m JOIN senales s ON s.id = m.senal_id JOIN equipos e ON e.id = s.equipo_id
                  WHERE e.equipo = %s AND s.nombre = ANY(%s) AND m.ts > now() - make_interval(mins => %s))
               SELECT nombre, to_char(ts AT TIME ZONE 'America/Lima', 'YYYY-MM-DD HH24:MI:SS'), valor
                 FROM x WHERE n = 1 OR previo IS DISTINCT FROM valor ORDER BY ts""",
            (eq_id, claves, minutos))
        por: dict[str, list] = {}
        for nombre, hora, valor in filas:
            por.setdefault(nombre, []).append({"hora_lima": hora, "valor": valor})
        return {"modulo": modulo, "ventana_min": minutos, "zona": "America/Lima",
                "nota": "el primer registro de cada señal es su valor al inicio de la ventana; los demás son cambios",
                "origen": "valores leídos del PLC por el conector edge y guardados por el ingestor",
                "catalogo": {k: {"direccion": catalogo.get(k, {}).get("direccion"),
                                 "descripcion": catalogo.get(k, {}).get("descripcion"),
                                 "hipotesis": bool(catalogo.get(k, {}).get("hipotesis", False))} for k in por},
                "senales": por}

    @mcp.tool()
    def historial_alarmas(minutos: int = 60) -> dict:
        """Historial (base de datos) de las ALARMAS del módulo: cuándo se activó y desactivó cada una en los
        últimos N minutos. Úsala si la pregunta habla del pasado ("estaba", "hace un rato", "a las 17:28")."""
        claves = [c for c in catalogo if c.startswith(("alarma/", "falla/")) or "/alarma_" in c
                  or c in {k for k, _, _ in _ALARMAS_SCADA} or c == "nivel/fuera_rango_sensor"]
        try:
            r = _cambios(claves, minutos)
        except Exception as ex:  # noqa: BLE001
            return {"error": str(ex)[:200]}
        r["valor_que_es_alarma"] = {k: malo for k, malo, _ in _ALARMAS_SCADA if k in claves}
        return r

    @mcp.tool()
    def historial_senal(clave: str, minutos: int = 60) -> dict:
        """Historial (base de datos) de UNA señal del módulo: su valor al inicio de la ventana y cada cambio."""
        if clave not in catalogo:
            return {"error": f"señal desconocida en {modulo}: {clave}"}
        try:
            return _cambios([clave], minutos)
        except Exception as ex:  # noqa: BLE001
            return {"error": str(ex)[:200]}

    @mcp.tool()
    def diagnostico() -> dict:
        """Diagnóstico DETERMINISTA: comunicación, frescura, alarmas activas, selector y marcha. No inventa bandas sin consigna."""
        eq = _equipo()
        valores = _valores()
        hallazgos: list[dict] = []
        if eq is None or eq.get("status") != "ONLINE":
            hallazgos.append({"severidad": "alarma", "hallazgo": "Sin comunicación fresca con el PLC",
                              "evidencia": f"estado={None if eq is None else eq.get('status')}"})
        if eq is not None and eq.get("calidad") not in (None, "buena"):
            hallazgos.append({"severidad": "alarma", "hallazgo": f"Calidad del dato: {eq.get('calidad')}",
                              "evidencia": "el valor principal no es una medida válida"})
        for clave, v in sorted(valores.items()):
            es_alarma = clave.startswith(("alarma/", "falla/")) or "/alarma_" in clave
            if es_alarma and v is True:
                hallazgos.append({"severidad": "alarma", "hallazgo": clave,
                                  "evidencia": catalogo.get(clave, {}).get("descripcion", ""),
                                  "direccion": catalogo.get(clave, {}).get("direccion"),
                                  "hipotesis": bool(catalogo.get(clave, {}).get("hipotesis", False)),
                                  "origen": "valor leído del PLC por el conector edge (no es una inferencia)"})
        # Indicadores de nivel que el SCADA pinta como ALARMA (lienzo/nodos.tsx) aunque su clave no empiece por alarma/
        for clave, valor_malo, texto in _ALARMAS_SCADA:
            if clave in valores and valores.get(clave) is valor_malo:
                hallazgos.append({"severidad": "alarma", "hallazgo": texto,
                                  "evidencia": f"{clave} = {valores.get(clave)} · {catalogo.get(clave, {}).get('descripcion', '')}".strip(" ·"),
                                  "senal": clave, "direccion": catalogo.get(clave, {}).get("direccion"),
                                  "hipotesis": bool(catalogo.get(clave, {}).get("hipotesis", False)),
                                  "origen": "valor leído del PLC por el conector edge (no es una inferencia)"})
        if valores.get("nivel/fuera_rango_sensor") is True:
            hallazgos.append({"severidad": "alarma", "hallazgo": "Sensor de nivel fuera de rango",
                              "evidencia": "el valor en cm es el tope de la escala, no una medida"})
        remoto, local = _bool(valores, "estado/selector_remoto"), _bool(valores, "estado/selector_local")
        selector = "REMOTO" if remoto else "LOCAL" if local else "EN 0 / desconocido"
        marcha = next((_bool(valores, k) for k in ("estado/sistema_funcionando", "estado/bomba_marcha")
                       if _bool(valores, k) is not None), None)
        valor, sp = (eq or {}).get("value"), (eq or {}).get("setpoint")
        desviacion = None
        if isinstance(valor, (int, float)) and isinstance(sp, (int, float)) and sp > 0 and marcha:
            desviacion = round(valor - sp, 2)
            if abs(desviacion) > abs(sp) * 0.12:
                hallazgos.append({"severidad": "advertencia", "hallazgo": "Variable fuera de banda (±12 % de la consigna)",
                                  "evidencia": f"valor {valor} vs consigna {sp}"})
        sev = "alarma" if any(h["severidad"] == "alarma" for h in hallazgos) else \
              "advertencia" if hallazgos else "normal"
        return {"modulo": modulo, "severidad": sev, "selector": selector, "en_marcha": marcha,
                "valor": valor, "consigna": sp, "desviacion": desviacion, "hallazgos": hallazgos,
                "metodo": "reglas deterministas (sin IA)", "solo_lectura": True}

    @mcp.tool()
    def metadatos() -> dict:
        """Identificación del módulo: código, PLC, IP, protocolo y tópico UNS."""
        return {"modulo": modulo, "equipo": eq_id, "codigo": cfg["codigo"], "plc": cfg["plc"], "ip": cfg["ip"],
                "protocolo": cfg["protocolo"], "uns_base": cfg["base_uns"], "herramientas": "solo lectura"}

    @mcp.tool()
    def grafo_conocimiento() -> dict:
        """Conocimiento del proceso: componentes, relaciones (qué alimenta/protege/controla a qué) y notas del laboratorio."""
        return {"modulo": modulo, "nodos": con["nodos"], "relaciones": con["relaciones"], "texto": con["conocimiento"]}

    @mcp.tool()
    def calidad_frescura() -> dict:
        """Edad del último dato y si la telemetría está fresca (≤ 30 s)."""
        eq = _equipo() or {}
        edad = _edad(eq.get("timestamp"))
        return {"modulo": modulo, "timestamp": eq.get("timestamp"), "edad_segundos": edad,
                "fresca": edad is not None and edad <= FRESCURA_MAX_S, "max_segundos": FRESCURA_MAX_S,
                "estado": eq.get("status"), "calidad": eq.get("calidad")}

    return mcp


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Servidor MCP (solo lectura) de un módulo")
    ap.add_argument("--modulo", required=True, choices=list(MODULOS))
    ap.add_argument("--puerto", type=int, default=None)
    a = ap.parse_args()
    srv = crear_servidor(a.modulo, a.puerto)
    print(f"[mcp-{a.modulo}] SSE en 0.0.0.0:{srv.settings.port} · backend {BACKEND} (solo lectura)", flush=True)
    srv.run(transport="sse")
