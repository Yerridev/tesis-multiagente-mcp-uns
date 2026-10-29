"""
Experimento de la tesis: agente unico (A) vs multiagente centralizado (B) vs hibrido (C).

Uso (desde historiador/, con Docker corriendo):
  python -m orquestacion.experimento --solo-verdad                       # revisa la verdad de campo, sin LLM
  python -m orquestacion.experimento --modelos gemini-flash --preguntas L01,D17,P01      # prueba corta
  python -m orquestacion.experimento --modelos gemini-flash,ollama                      # experimento completo
  python -m orquestacion.experimento --continuar logs/experimento/20261029_1530         # reanuda una corrida
  python -m orquestacion.experimento --resumen logs/experimento/20261029_1530           # solo rehace el resumen

Opciones: --configs A,B,C,D   --repeticiones 1   --sin-verificador (B, C y D sin verificador: ablacion)
          --preguntas L01,D17 | tipo:2   --timeout 420

Salida en logs/experimento/<fecha>/: resultados.jsonl (una fila por corrida), trazas/*.json (pasos y salidas de
herramientas), resumen.md y resumen.csv (metricas por modelo y configuracion).

Puntuacion:
- Exactitud estricta: con el bloque json final (valor dentro de la tolerancia en tipo 1; diagnostico igual al
  esperado por equipo en tipos 2 y 3). Exactitud tolerante: busca el valor o el codigo en el texto completo.
- Fundamentacion: % de cifras del texto que aparecen en alguna salida real de herramienta (se excluyen fechas, horas,
  cifras presentes en la propia pregunta y enteros de 0 a 10).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent          # historiador/
sys.path.insert(0, str(RAIZ))

from orquestacion.agentes import extraer_json  # noqa: E402
from orquestacion.mcp_pool import leer_registro  # noqa: E402

TZ_LIMA = timezone(timedelta(hours=-5))
PREGUNTAS = Path(__file__).resolve().parent / "preguntas.json"
NUM = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")
FECHA_HORA = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2})?)?|\d{1,2}:\d{2}(?::\d{2})?"
                        r"|\d{1,2}[-/ ](?:de )?[a-z]{3,10}[-/ ](?:de )?\d{4}", re.I)


# ----------------------------------------------------------------------------- entorno
def cargar_env() -> dict:
    cfg = {}
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in cfg.items():
        os.environ.setdefault(k, v)
    return cfg


def dsn_lector(cfg: dict) -> str:
    return os.getenv("MCP_DSN") or (f"postgresql://mcp_lector:{cfg.get('MCP_READER_PASSWORD', '')}@localhost:5432/"
                                    f"{cfg.get('DB_NAME', 'uns')}")


def momento_lima(s: str) -> datetime:
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=TZ_LIMA)


# ----------------------------------------------------------------------------- verdad de campo
def verdad_tipo1(dsn: str, preguntas: list[dict]) -> dict[str, dict]:
    """Valor real en la base para cada pregunta de tipo 1 (ultimo dato 'uns' en los 180 s previos)."""
    import psycopg

    prefijos = {e["alias"]: e.get("prefijo_db", "") for e in leer_registro()}
    out = {}
    with psycopg.connect(dsn, connect_timeout=5, options="-c default_transaction_read_only=on") as con:
        for q in preguntas:
            if q["tipo"] != 1:
                continue
            var = prefijos.get(q["equipo"], "") + q["variable"]
            t = momento_lima(q["momento"])
            fila = con.execute("SELECT valor, time FROM mediciones WHERE variable = %s AND fuente = 'uns' "
                               "AND time <= %s AND time > %s - interval '180 seconds' ORDER BY time DESC LIMIT 1",
                               (var, t, t)).fetchone()
            out[q["id"]] = {"variable": var, "valor": float(fila[0]) if fila else None,
                            "hora_dato": fila[1].astimezone(TZ_LIMA).isoformat(timespec="seconds") if fila else None}
    return out


def revisar_verdad(dsn: str, preguntas: list[dict]) -> None:
    """Sin LLM: muestra la verdad de tipo 1 y compara las de tipos 2 y 3 con el diagnostico determinista."""
    sys.path.insert(0, str(RAIZ / "mcp_servidor"))
    os.environ["MCP_DSN"] = dsn
    import importlib

    reg = {e["alias"]: e for e in leer_registro()}
    v1 = verdad_tipo1(dsn, preguntas)
    print("\n== Tipo 1: valor en la base ==")
    for q in preguntas:
        if q["tipo"] == 1:
            v = v1[q["id"]]
            print(f"  {q['id']}  {v['variable']:<42} {q['momento']}  ->  {v['valor']}  (dato de {v['hora_dato']})"
                  + ("   <-- SIN DATO: se excluira" if v["valor"] is None else ""))
    print("\n== Tipos 2 y 3: esperado vs diagnostico determinista del servidor MCP ==")
    mods = {}
    for q in preguntas:
        if q["tipo"] == 1:
            continue
        momentos = ({q["equipo"]: q["momento"]} if q["tipo"] == 2 else _momentos_p(q))
        for alias, esperado in q["esperado"].items():
            e = reg[alias]
            mods.setdefault(alias, importlib.import_module(e["mcp_modulo"]))
            m = momentos.get(alias)
            try:
                r = getattr(mods[alias], e["diagnostico"])(m)
                ok = "OK " if r["diagnostico"] == esperado else "DIF"
                print(f"  {q['id']}  {alias:<12} {m}  esperado={esperado:<28} determinista={r['diagnostico']}  {ok}")
            except Exception as ex:  # noqa: BLE001
                print(f"  {q['id']}  {alias:<12} {m}  ERROR: {ex}")


def _momentos_p(q: dict) -> dict:
    """Momento de cada equipo en una pregunta de tipo 3 (campo 'momentos' de preguntas.json)."""
    return q.get("momentos", {})


# ----------------------------------------------------------------------------- puntuacion
def _numeros(texto: str) -> list[float]:
    limpio = FECHA_HORA.sub(" ", texto or "")
    limpio = re.sub(r"\b[a-z]+-?[a-z]*\d+\b", " ", limpio, flags=re.I)   # ids como mcc09, mcp-09, AIO-610
    out = []
    for m in NUM.finditer(limpio):
        try:
            out.append(float(m.group(0).replace(",", ".")))
        except ValueError:
            pass
    return out


def _cerca(n: float, e: float) -> bool:
    if abs(n - e) <= max(0.051, 0.006 * abs(e)):
        return True
    dec = len(str(n).split(".")[1]) if "." in str(n) else 0
    return round(e, dec) == n


def fundamentacion(respuesta: str, pregunta: str, evidencia: list[str]) -> dict:
    cifras = [n for n in _numeros(respuesta) if not (float(n).is_integer() and 0 <= n <= 10)]
    de_pregunta = set(_numeros(pregunta))
    cifras = [n for n in cifras if n not in de_pregunta]
    ev = []
    for t in evidencia:
        ev.extend(_numeros(t))
    sin = [n for n in cifras if not any(_cerca(n, e) for e in ev)]
    total = len(cifras)
    return {"cifras": total, "sin_fundamento": len(sin), "ejemplos_sin_fundamento": sin[:8],
            "pct": round(100 * (total - len(sin)) / total, 1) if total else 100.0}


def _alias(eq, reg: dict) -> str | None:
    eq = str(eq or "").lower()
    return next((a for a, e in reg.items() if eq in (a, e["id"]) or eq.startswith(a)), None)


def _diag_por_equipo(js: dict | None, reg: dict, momentos: dict | None = None) -> dict:
    """Diagnostico por equipo. Si la pregunta fija el momento de cada equipo, se puntua la entrada de ESE momento
    (a la resolucion del minuto); si no hay una entrada con ese momento, la ultima del equipo."""
    out, exactos = {}, {}
    for item in (js or {}).get("equipos", []) or []:
        if not isinstance(item, dict):
            continue
        eq = str(item.get("equipo", "")).lower()
        alias = next((a for a, e in reg.items() if eq in (a, e["id"]) or eq.startswith(a)), None)
        if alias and item.get("diagnostico"):
            d = str(item["diagnostico"]).strip().upper()
            out[alias] = d
            esperado = (momentos or {}).get(alias)
            if esperado and str(item.get("momento", ""))[:16] == esperado[:16]:
                exactos[alias] = d
    return {**out, **exactos}


def puntuar(q: dict, r: dict, verdad1: dict, reg: dict) -> dict:
    js = r.get("json")
    texto = r.get("respuesta") or ""
    p = {"formato_ok": isinstance(js, dict) and isinstance(js.get("equipos"), list)}
    if q["tipo"] == 1:
        v = verdad1.get(q["id"], {}).get("valor")
        if v is None:
            return {**p, "evaluable": False}
        # El nombre de la clave lo elige el modelo ('caudal/setpoint', 'setpoint_c'...): se puntuan los numeros
        # del bloque json del equipo preguntado (o de todos si no lo identifica), no el nombre de la clave.
        items = [i for i in (js or {}).get("equipos", []) or [] if isinstance(i, dict)
                 and isinstance(i.get("valores"), dict)]
        del_equipo = [i for i in items if _alias(i.get("equipo"), reg) == q["equipo"]]
        cand = [x for i in (del_equipo or items) for x in i["valores"].values()
                if isinstance(x, (int, float)) and not isinstance(x, bool)]
        estricto = any(abs(x - v) <= q["tolerancia"] for x in cand)
        tolerante = estricto or any(abs(x - v) <= q["tolerancia"] for x in _numeros(texto))
        return {**p, "evaluable": True, "verdad": v, "correcto": estricto, "correcto_tolerante": tolerante,
                "fraccion": 1.0 if estricto else 0.0}
    momentos = q.get("momentos") or ({q["equipo"]: q["momento"]} if q.get("momento") else {})
    obtenidos = _diag_por_equipo(js, reg, momentos)
    aciertos = {a: obtenidos.get(a) == d for a, d in q["esperado"].items()}
    tolerantes = {a: aciertos[a] or (d in texto.upper()) for a, d in q["esperado"].items()}
    return {**p, "evaluable": True, "verdad": q["esperado"], "obtenido": obtenidos,
            "correcto": all(aciertos.values()), "correcto_tolerante": all(tolerantes.values()),
            "fraccion": round(sum(aciertos.values()) / len(aciertos), 3)}


# ----------------------------------------------------------------------------- corrida
def _sin_saldo(e: Exception) -> bool:
    t = str(e).lower()
    return getattr(e, "status_code", None) == 402 or "credits" in t or "insufficient_quota" in t


def _clave(f: dict) -> tuple:
    return (f["modelo"], f["config"], f["pregunta"], f["rep"])


async def correr(args, preguntas: list[dict], dsn: str, salida: Path) -> None:
    from orquestacion.llm import ClienteLLM
    from orquestacion.mcp_pool import PoolMCP
    from orquestacion.orquestador import responder

    reg = {e["alias"]: e for e in leer_registro()}
    verdad1 = verdad_tipo1(dsn, preguntas)
    (salida / "verdad_tipo1.json").write_text(json.dumps(verdad1, ensure_ascii=False, indent=2), encoding="utf-8")
    (salida / "trazas").mkdir(parents=True, exist_ok=True)
    archivo = salida / "resultados.jsonl"
    hechas = set()
    if archivo.exists():  # --continuar: se conservan las corridas validas y se repiten las que dieron error
        validas = [x for x in (json.loads(l) for l in archivo.read_text(encoding="utf-8").splitlines() if l.strip())
                   if "error" not in x]
        archivo.write_text("".join(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in validas),
                           encoding="utf-8")
        hechas = {_clave(x) for x in validas}
    configs = args.configs.split(",")
    total = len(args.modelos.split(",")) * len(configs) * len(preguntas) * args.repeticiones
    n = len(hechas)
    for modelo in args.modelos.split(","):
        llm = ClienteLLM(modelo)
        async with PoolMCP(dsn) as pool:
            for q in preguntas:
                if q["tipo"] == 1 and verdad1.get(q["id"], {}).get("valor") is None:
                    print(f"  {q['id']}: sin dato en la base, se omite")
                    continue
                for rep in range(1, args.repeticiones + 1):
                    for config in configs:
                        etiqueta = config + ("-sv" if args.sin_verificador and config in "BCD" else "")
                        fila = {"modelo": modelo, "modelo_nombre": llm.modelo, "config": etiqueta, "pregunta": q["id"],
                                "tipo": q["tipo"], "rep": rep}
                        if _clave(fila) in hechas:
                            continue
                        n += 1
                        t0 = time.perf_counter()
                        try:
                            r = await asyncio.wait_for(responder(config, q["texto"], llm, pool,
                                                                 verificar=not args.sin_verificador),
                                                       timeout=args.timeout)
                            evid = [h["texto"] for h in r["traza"]["herramientas"]]
                            fila.update({"respuesta": r["respuesta"], "json": r["json"], "ruta": r["ruta"],
                                         "latencia_s": r["latencia_s"], "uso": r["uso"],
                                         "llamadas_herramientas": r["llamadas_herramientas"],
                                         "herramientas_con_error": r["herramientas_con_error"],
                                         "puntuacion": puntuar(q, r, verdad1, reg),
                                         "fundamentacion": fundamentacion(r["respuesta"], q["texto"], evid)})
                            nombre = f"{modelo}_{etiqueta}_{q['id']}_r{rep}.json"
                            (salida / "trazas" / nombre).write_text(
                                json.dumps({"pregunta": q, **r}, ensure_ascii=False, indent=1, default=str),
                                encoding="utf-8")
                        except Exception as e:  # noqa: BLE001
                            if _sin_saldo(e):  # no es un resultado del experimento: se detiene sin registrar
                                print(f"\n[DETENIDO] El proveedor rechazo la peticion por saldo o limite de gasto: {e}"[:400])
                                print(f"Recarga y repite con:  EXPERIMENTO.bat ... --continuar {salida}")
                                return
                            fila.update({"error": f"{type(e).__name__}: {e}"[:500],
                                         "latencia_s": round(time.perf_counter() - t0, 2)})
                        with archivo.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
                        pt = fila.get("puntuacion", {})
                        estado = ("ERROR " + fila["error"][:60]) if "error" in fila else \
                            f"{'OK ' if pt.get('correcto') else 'NO '} fund {fila['fundamentacion']['pct']}%  " \
                            f"{fila['latencia_s']} s  {fila['uso']['peticiones']} pet"
                        print(f"[{n}/{total}] {modelo:<18} {etiqueta:<4} {q['id']}  {estado}", flush=True)


# ----------------------------------------------------------------------------- resumen
def resumir(salida: Path) -> None:
    filas = [json.loads(x) for x in (salida / "resultados.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    grupos = defaultdict(list)
    for f in filas:
        grupos[(f["modelo"], f["config"])].append(f)

    def media(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.mean(xs), 2) if xs else None

    filas_res = []
    for (modelo, config), fs in sorted(grupos.items()):
        ok = [f for f in fs if "error" not in f and f.get("puntuacion", {}).get("evaluable")]
        fila = {"modelo": modelo, "config": config, "corridas": len(fs), "errores": sum("error" in f for f in fs),
                "exactitud_%": media([100 * f["puntuacion"]["correcto"] for f in ok]),
                "exactitud_tolerante_%": media([100 * f["puntuacion"]["correcto_tolerante"] for f in ok]),
                "fundamentacion_%": media([f["fundamentacion"]["pct"] for f in ok]),
                "formato_ok_%": media([100 * f["puntuacion"]["formato_ok"] for f in ok]),
                "herramientas_media": media([f["llamadas_herramientas"] for f in ok]),
                "peticiones_media": media([f["uso"]["peticiones"] for f in ok]),
                "tokens_media": media([f["uso"]["tokens_total"] for f in ok]),
                "latencia_mediana_s": round(statistics.median([f["latencia_s"] for f in ok]), 1) if ok else None}
        for t in (1, 2, 3):
            fila[f"exactitud_tipo{t}_%"] = media([100 * f["puntuacion"]["correcto"] for f in ok if f["tipo"] == t])
            fila[f"latencia_tipo{t}_s"] = media([f["latencia_s"] for f in ok if f["tipo"] == t])
        filas_res.append(fila)
    if not filas_res:
        print("Sin resultados")
        return
    with (salida / "resumen.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_res[0]))
        w.writeheader()
        w.writerows(filas_res)
    cols = ["modelo", "config", "corridas", "errores", "exactitud_%", "exactitud_tipo1_%", "exactitud_tipo2_%",
            "exactitud_tipo3_%", "exactitud_tolerante_%", "fundamentacion_%", "formato_ok_%", "herramientas_media",
            "peticiones_media", "tokens_media", "latencia_mediana_s", "latencia_tipo3_s"]
    md = [f"# Resultados del experimento ({salida.name})", "",
          "A = agente unico · B = coordinador LLM + agentes de equipo + verificador · C = enrutador por reglas + "
          "agentes de equipo + verificador · D = roles del lienzo (consulta, diagnostico, reporte) + coordinador + "
          "verificador · -sv = sin verificador", "",
          "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in filas_res]
    fallos = [f for f in filas if "error" in f or not f.get("puntuacion", {}).get("correcto", True)]
    md += ["", f"## Respuestas incorrectas o con error ({len(fallos)})", "",
           "| Modelo | Config | Pregunta | Esperado | Obtenido / error |", "|---|---|---|---|---|"]
    for f in fallos:
        p = f.get("puntuacion", {})
        md.append(f"| {f['modelo']} | {f['config']} | {f['pregunta']} | {p.get('verdad', '')} | "
                  f"{f.get('error') or p.get('obtenido') or (f.get('json') or {}).get('respuesta', '')} |")
    (salida / "resumen.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:len(filas_res) + 6]))
    print(f"\n-> {salida / 'resumen.md'}")


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="Experimento A/B/C de orquestacion multiagente")
    ap.add_argument("--modelos", default="gemini-flash", help="perfiles de modelos.json separados por coma")
    ap.add_argument("--configs", default="A,B,C")
    ap.add_argument("--preguntas", default="", help="ids separados por coma o tipo:N; vacio = todas")
    ap.add_argument("--repeticiones", type=int, default=1)
    ap.add_argument("--sin-verificador", action="store_true")
    ap.add_argument("--timeout", type=float, default=420)
    ap.add_argument("--continuar", default="", help="carpeta de una corrida anterior para reanudarla")
    ap.add_argument("--resumen", default="", help="solo regenera el resumen de esa carpeta")
    ap.add_argument("--solo-verdad", action="store_true", help="revisa la verdad de campo sin llamar al LLM")
    args = ap.parse_args()

    if args.resumen:
        resumir(Path(args.resumen))
        return
    cfg = cargar_env()
    dsn = dsn_lector(cfg)
    todas = json.loads(PREGUNTAS.read_text(encoding="utf-8"))["preguntas"]
    if args.preguntas.startswith("tipo:"):
        preguntas = [q for q in todas if q["tipo"] == int(args.preguntas[5:])]
    elif args.preguntas:
        ids = set(args.preguntas.split(","))
        preguntas = [q for q in todas if q["id"] in ids]
    else:
        preguntas = todas
    if args.solo_verdad:
        revisar_verdad(dsn, preguntas)
        return
    salida = Path(args.continuar) if args.continuar else \
        RAIZ / "logs" / "experimento" / datetime.now(TZ_LIMA).strftime("%Y%m%d_%H%M")
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "parametros.json").write_text(json.dumps(vars(args), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Corrida en {salida}  ({len(preguntas)} preguntas)")
    asyncio.run(correr(args, preguntas, dsn, salida))
    resumir(salida)


if __name__ == "__main__":
    main()
