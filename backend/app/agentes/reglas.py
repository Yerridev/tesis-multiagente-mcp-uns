"""Agente de supervisión por reglas deterministas (sin IA).

Port de ``PlantState.Ask()`` y ``PlantState.BuildSystemContext()``.  Estas
reglas son la respuesta de reserva cuando no hay clave de OpenRouter, cuando
el modelo falla, y también el contexto que se le pasa al modelo.

Punto clave: el agente **solo lee**.  Nunca dice que ejecutó una orden.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..estado.planta import (
    CALIDAD_BUENA,
    CALIDAD_FUERA_DE_RANGO,
    CALIDAD_SIN_CALIDAD,
    PlantState,
)

#: Perú no tiene horario de verano: UTC-5 fijo.
HORA_LIMA = timezone(timedelta(hours=-5))


def _sin_acentos(texto: str) -> str:
    """Quita los acentos para comparar sin tildes."""
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c)).lower()


def _coincide(texto: str, patron: str) -> bool:
    return re.search(_sin_acentos(patron), _sin_acentos(texto)) is not None


def _clave_de(equipo_id: str) -> str:
    return equipo_id.split("-")[0]


def _hora_lima(momento: datetime | None) -> str:
    if momento is None:
        return "--:--:--"
    return momento.astimezone(HORA_LIMA).strftime("%H:%M:%S")


# --------------------------------------------------------------------------- reglas
def preguntar(planta: PlantState, mensaje: str | None) -> dict[str, Any]:
    """Responde con datos reales del estado y del historial. Solo lectura."""
    texto = (mensaje or "").strip()
    norm = _sin_acentos(texto)
    llamadas: list[dict[str, Any]] = []
    respuesta = ""

    def _llamada(nombre: str, accion: Callable[[], str]) -> None:
        nonlocal respuesta
        import time

        inicio = time.perf_counter()
        try:
            resultado = accion()
            ok = True
        except Exception as exc:              # pragma: no cover
            resultado = str(exc)
            ok = False
        ms = int((time.perf_counter() - inicio) * 1000)
        llamadas.append({"name": nombre, "ok": ok, "ms": ms, "result": resultado})

    if not norm or _coincide(norm, r"hola|ayuda|qué puedes|que puedes|help"):
        respuesta = (
            "Soy el agente de supervisión de MCP Industrial. Puedo responder sobre el estado de "
            "los equipos, las alarmas, el historial y el PLC 192.168.114.9. Ejemplos: «estado de "
            "la planta», «¿hay alarmas?», «promedio de caudal», «estado del PLC». Solo lectura: "
            "no envío órdenes al PLC."
        )
        _llamada("ayuda", lambda: "listado de capacidades")

    elif _coincide(norm, r"\blocal\b|remoto|selector|modo de (control|operaci)"):
        def _modo() -> str:
            nonlocal respuesta
            detalle = planta.detalle_nivel()
            if detalle["mode"] is None:
                respuesta = "No tengo el dato del selector del módulo de nivel en este momento."
            else:
                respuesta = (
                    f"El módulo de nivel (MicroLogix 1100) está en modo {detalle['mode']}. "
                    + ("Manda la PC/SCADA (PID del PLC)."
                       if str(detalle["mode"]).upper() == "REMOTO"
                       else "Manda el tablero: potenciómetro y pulsadores.")
                )
            return str(detalle["mode"] or "sin dato")

        _llamada("modo_selector", _modo)

    elif _coincide(norm, r"histor|promedio|prom |media|mínim|minim|máxim|maxim|tendencia"):
        def _historial() -> str:
            nonlocal respuesta
            objetivo = next((e for e in planta.todos() if _coincide(norm, _clave_de(e["id"]))), None)
            if objetivo is None:
                objetivo = next((e for e in planta.todos() if e["id"] == "caudal-mcc09"), None)
            if objetivo is None:              # pragma: no cover
                return "sin muestras"
            muestras = planta.historial(objetivo["id"], 1800)
            if not muestras:
                return "sin muestras"
            valores = [m["value"] for m in muestras]
            minimo, maximo = min(valores), max(valores)
            promedio = round(sum(valores) / len(valores), 2)
            respuesta = (
                f"Historial de {objetivo['variable'].lower()} ({len(muestras)} muestras): "
                f"mínimo {minimo} {objetivo['unit']}, promedio {promedio} {objetivo['unit']}, "
                f"máximo {maximo} {objetivo['unit']}. Consigna {objetivo['setpoint']} "
                f"{objetivo['unit']}."
            )
            return f"{len(muestras)} muestras · min {minimo} · avg {promedio} · max {maximo}"

        _llamada("resumen_historico", _historial)

    elif _coincide(norm, r"alarma|alarm|fuera de rango|exceso"):
        def _alarmas() -> str:
            nonlocal respuesta
            equipos = planta.todos()
            alarmas = [f"{e['name']} ({e['value']} {e['unit']} vs {e['setpoint']} {e['unit']})"
                       for e in equipos if e["alarm"]]
            detalle = planta.detalle_nivel()
            etiquetas: list[str] = []
            if detalle["highAlarm"] is True:
                etiquetas.append("nivel alto")
            if detalle["lowAlarm"] is True:
                etiquetas.append("nivel bajo")
            no_medibles = [f"{e['name']} (sensor fuera de rango)"
                           for e in equipos if e["calidad"] != CALIDAD_BUENA]
            if no_medibles:
                respuesta = (
                    f"ATENCIÓN: hay {len(no_medibles)} equipo(s) con medida no válida por saturación "
                    f"del sensor: {'; '.join(no_medibles)}. El valor mostrado en cm es un artefacto "
                    "de la escala, NO el nivel real: verifica el sensor y el nivel físico antes de "
                    "operar. "
                    + ("Sin alarmas activas."
                       if not alarmas and not etiquetas
                       else f"Alarmas activas: {('ninguna en equipo' if not alarmas else '; '.join(alarmas))}"
                            f"{('; tanque: ' + ', '.join(etiquetas)) if etiquetas else ''}.")
                )
            elif not alarmas and not etiquetas:
                respuesta = ("Sin alarmas activas. Todos los equipos operan dentro de la banda de "
                             "±12 % de su consigna y el tanque no reporta nivel alto ni bajo.")
            else:
                respuesta = (
                    "Alarmas activas: "
                    f"{('ninguna en equipo' if not alarmas else '; '.join(alarmas))}"
                    f"{('; tanque: ' + ', '.join(etiquetas)) if etiquetas else ''}."
                )
            return (f"{len(alarmas)} equipos + {len(etiquetas)} de tanque "
                    f"+ {len(no_medibles)} no medibles")

        _llamada("verificar_alarma", _alarmas)

    elif _coincide(norm, r"plc|micrologix|114\.9|comunic"):
        def _plc() -> str:
            nonlocal respuesta
            detalle = planta.detalle_nivel()
            if detalle["calidad"] != CALIDAD_BUENA:
                respuesta = (
                    f"PLC {detalle['controller']} en {detalle['plcIp']}: {detalle['plcStatus']}. "
                    f"Última lectura {_hora_lima(detalle['timestamp'])}. SENSOR DE NIVEL FUERA DE "
                    "RANGO: el nivel no es medible (el valor en cm es saturación de la escala); "
                    "revisa el sensor y el nivel físico antes de controlar."
                )
            else:
                respuesta = (
                    f"PLC {detalle['controller']} en {detalle['plcIp']}: {detalle['plcStatus']}. "
                    f"Última lectura {_hora_lima(detalle['timestamp'])}, nivel {detalle['level']} "
                    f"{detalle['unit']} (consigna {detalle['setpoint']} {detalle['unit']}, "
                    f"{detalle['percent']} % del tanque)."
                )
            return f"{detalle['plcStatus']} · {_hora_lima(detalle['timestamp'])} · calidad {detalle['calidad']}"

        _llamada("estado_plc", _plc)

    elif _coincide(norm, r"equipo|caudal|nivel|presi|temp|valor|módulo|modulo"):
        objetivo = next((e for e in planta.todos() if _coincide(norm, _clave_de(e["id"]))), None)
        if objetivo is None:
            def _planta() -> str:
                nonlocal respuesta
                partes = []
                for e in planta.todos():
                    if e["calidad"] == CALIDAD_BUENA and e["value"] is not None:
                        partes.append(f"{e['variable']} {e['value']} {e['unit']} "
                                      f"(consigna {e['setpoint']}, {e['status']})")
                    else:
                        partes.append(f"{e['variable']} NO MEDIBLE (sensor fuera de rango; el valor "
                                      f"en {e['unit']} sería saturación de la escala)")
                respuesta = " · ".join(partes)
                return f"{len(planta.todos())} equipos"

            _llamada("estado_planta", _planta)
        else:
            def _equipo() -> str:
                nonlocal respuesta
                vivo = planta.obtener(objetivo["id"]) or objetivo
                if vivo["calidad"] != CALIDAD_BUENA or vivo["value"] is None:
                    respuesta = (
                        f"{vivo['name']} · {vivo['controller']} ({vivo['ip']}): {vivo['variable']} "
                        "NO MEDIBLE (sensor fuera de rango). El valor publicado "
                        f"({vivo['value']} {vivo['unit']}) es saturación de la escala, no el nivel "
                        f"real; verifica el sensor y el nivel físico. Estado {vivo['status']}."
                    )
                else:
                    respuesta = (
                        f"{vivo['name']} · {vivo['controller']} ({vivo['ip']}): {vivo['variable']} = "
                        f"{vivo['value']} {vivo['unit']} (consigna {vivo['setpoint']} {vivo['unit']}, "
                        f"desviación {vivo['deviation']} {vivo['unit']}, estado {vivo['status']}, "
                        f"alarma {'ACTIVA' if vivo['alarm'] else 'sin alarma'})."
                    )
                return f"{vivo['value']} {vivo['unit']} · consigna {vivo['setpoint']} · {vivo['status']}"

            _llamada("leer_equipo", _equipo)

    if not respuesta.strip():
        respuesta = ("No dispongo de datos para esa consulta. Prueba con «estado de la planta», "
                     "«alarmas», «promedio de caudal» o «estado del PLC».")

    return {"reply": respuesta, "agent": "Agente de supervisión MCP",
            "tools": llamadas, "mode": "rules"}


# --------------------------------------------------------------------------- contexto
def contexto_sistema(planta: PlantState) -> str:
    """Prompt de sistema con los datos en vivo para el modelo de OpenRouter."""
    lineas: list[str] = []
    lineas.append(
        "Eres el agente de supervisión de MCP Industrial (Laboratorio USS · UNS). Trabajas en MODO "
        "SOLO LECTURA: no propongas órdenes de arranque, parada ni cambios de consigna; la lógica "
        "de control y seguridad vive en el PLC."
    )
    lineas.append("Responde en español, de forma breve y sin inventar: usa SOLO los datos en vivo "
                  "de abajo. Si algo no aparece, dilo.")
    lineas.append("Datos en vivo:")
    for equipo in planta.todos():
        if equipo["calidad"] != CALIDAD_BUENA or equipo["value"] is None:
            lineas.append(
                f"- {equipo['name']} [{equipo['id']}] · {equipo['controller']} ({equipo['ip']}): "
                f"MEDIDA NO VÁLIDA (sensor fuera de rango). El valor publicado "
                f"({equipo['value']} {equipo['unit']}) es el tope de saturación de la escala, NO el "
                "nivel real. No lo reportes como un nivel ni lo compares con una consigna: dilo así, "
                "sin inventar."
            )
            continue
        lineas.append(
            f"- {equipo['name']} [{equipo['id']}] · {equipo['controller']} ({equipo['ip']}): "
            f"{equipo['variable']} = {equipo['value']} {equipo['unit']}, consigna "
            f"{equipo['setpoint']} {equipo['unit']}, desviación {equipo['deviation']} "
            f"{equipo['unit']}, estado {equipo['status']}, alarma "
            f"{'ACTIVA' if equipo['alarm'] else 'sin alarma'}, última lectura "
            f"{_hora_lima(equipo['timestamp'])} (hora de Lima)."
        )

    detalle = planta.detalle_nivel()
    if detalle["calidad"] == CALIDAD_FUERA_DE_RANGO:
        lineas.append(
            "- Tanque MCN-09: SENSOR DE NIVEL FUERA DE RANGO (saturado). El nivel NO es medible; "
            "el valor en cm que aparece en la interfaz es un artefacto de la escala. Informa de la "
            "falla del sensor y de que el nivel debe verificarse físicamente; no informes un nivel."
        )
    elif detalle["calidad"] == CALIDAD_SIN_CALIDAD:
        lineas.append(
            "- Tanque MCN-09: calidad del dato de nivel aún no conocida (falta la lectura primaria "
            "del sensor). No hay nivel medible en este momento."
        )
    else:
        if detalle["level"] is None:
            lineas.append(
                f"- Tanque MCN-09: sin lecturas reales del PLC ({detalle['plcStatus']}). "
                f"Altura del tanque {detalle['tankHeight'] or 0} {detalle['unit']}."
            )
        else:
            extras = ""
            if detalle["tankHeight"] is not None:
                extras += f" sobre {detalle['tankHeight']} {detalle['unit']}"
            if detalle["percent"] is not None:
                extras += f" ({detalle['percent']} %)"
            extras += f", modo {detalle['mode'] or 'sin datos'}"
            extras += (", bomba encendida" if detalle["pumpOn"] is True
                       else (", bomba apagada" if detalle["pumpOn"] is False else ", bomba sin datos"))
            if detalle["vfdHz"] is not None:
                extras += f" a {detalle['vfdHz']} Hz"
            valve = ("sin datos" if detalle["valveOpen"] is None else f"{detalle['valveOpen']} %")
            lineas.append(
                f"- Tanque MCN-09: nivel {detalle['level']} {detalle['unit']}{extras}, "
                f"válvula {valve}, PLC {detalle['plcIp']} {detalle['plcStatus']}."
            )

    lineas.append(f"- Historial en memoria: {planta.resumen_historial()}")
    lineas.append("Los datos provienen del backend de supervisión: historial en memoria y "
                  "telemetría en vivo cuando el equipo reporta. Todo es de solo lectura: no se "
                  "envían órdenes al PLC.")
    return "\n".join(lineas)


#: Reglas de estilo del agente (las mismas del backend ASP.NET).
REGLAS = """Cómo responder:
- Responde DIRECTO a lo que se pregunta, en español y en 1 a 5 frases (más solo si piden detalle). Empieza por la respuesta, no por el contexto.
- Usa las señales en vivo de abajo; si una pregunta depende de una señal que no aparece o el módulo está SIN COMUNICACIÓN, dilo claramente en una frase. No añadas descargos innecesarios ("los datos no indican...") cuando el dato sí está.
- Interpreta las señales con su significado (p. ej. estado/selector_remoto = 1 → modo REMOTO). Si la señal está marcada [H], menciona que es una hipótesis.
- Usa la conversación previa para entender preguntas cortas ("¿y ahora?", "¿y el de caudal?").
- Nunca digas que ejecutaste una orden: eres de solo lectura; las órdenes se dan desde el SCADA con confirmación.
"""
