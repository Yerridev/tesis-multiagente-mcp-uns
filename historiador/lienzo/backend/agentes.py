"""Definición y planificación de los agentes especializados del lienzo.

Los agentes no tienen acceso directo a PLC, MQTT ni SQL. Solo reciben herramientas
MCP de lectura incluidas en su lista blanca. El coordinador no recibe herramientas:
su función es consolidar evidencia producida por los especialistas.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class AgenteRol:
    id: str
    nombre: str
    objetivo: str
    instrucciones: str
    herramientas: tuple[str, ...]

    def permite(self, herramienta: str) -> bool:
        return any(herramienta == p or herramienta.startswith(p) for p in self.herramientas)


AGENTES: dict[str, AgenteRol] = {
    "consulta": AgenteRol(
        id="consulta",
        nombre="Agente de consulta industrial",
        objetivo="Obtener mediciones, estados e históricos trazables sin interpretarlos más allá de la evidencia.",
        instrucciones=(
            "Usa las herramientas antes de responder. Entrega valor, unidad, instante o periodo, fuente y vigencia. "
            "No diagnostiques causas: limita la salida a hechos observados y advierte datos faltantes o desactualizados."
        ),
        herramientas=("listar_variables", "obtener_lectura", "obtener_estado_plc", "consultar_historial",
                      "comparar_con_rango"),
    ),
    "diagnostico": AgenteRol(
        id="diagnostico",
        nombre="Agente de diagnóstico industrial",
        objetivo="Explicar el estado del proceso mediante diagnósticos y relaciones causales respaldadas por datos.",
        instrucciones=(
            "Ejecuta primero la herramienta diagnosticar_* del equipo pertinente. Usa el grafo para relaciones causales "
            "y lecturas o históricos para confirmar. Separa hallazgo, evidencia, causa probable y limitaciones. "
            "No conviertas una hipótesis en certeza."
        ),
        herramientas=("diagnosticar_", "diagnosticar_lazo", "consultar_grafo", "obtener_estado_plc",
                      "obtener_lectura", "consultar_historial", "comparar_con_rango", "verificar_coherencia_"),
    ),
    "reporte": AgenteRol(
        id="reporte",
        nombre="Agente de reportes y trazabilidad",
        objetivo="Organizar evidencia histórica y comparativa en un resumen auditable.",
        instrucciones=(
            "Construye un reporte breve con alcance, periodo, fuentes, resultados por equipo, advertencias y conclusión. "
            "Conserva unidades y marcas de tiempo. No inventes valores ni completes huecos. Si comparas equipos, aclara "
            "cuando sus variables o escalas no sean equivalentes."
        ),
        herramientas=("consultar_historial", "obtener_lectura", "obtener_estado_plc", "comparar_con_rango",
                      "comparar_con_historico_", "diagnosticar_", "diagnosticar_lazo"),
    ),
    "coordinador": AgenteRol(
        id="coordinador",
        nombre="Agente coordinador",
        objetivo="Integrar las respuestas de especialistas sin alterar su evidencia.",
        instrucciones=(
            "Sintetiza las respuestas de los especialistas. Comienza con la conclusión, continúa con evidencia por equipo "
            "y termina con advertencias. Señala desacuerdos o datos insuficientes. No agregues mediciones que no aparezcan "
            "en la evidencia y no sugieras acciones de control sobre los PLC."
        ),
        herramientas=(),
    ),
}


_DIAGNOSTICO = re.compile(
    r"\b(por qu[eé]|causa|falla|fallo|alarma|diagn[oó]st|problema|anomal|no sigue|no funciona|advertencia)\b", re.I
)
_REPORTE = re.compile(
    r"\b(reporte|informe|resumen|compara|comparaci[oó]n|hist[oó]ric|evoluci[oó]n|tendencia|periodo|entre .* y)\b", re.I
)
_ESTADO_GENERAL = re.compile(r"\b(todos|general|laboratorio|equipos|cu[aá]l|estado actual)\b", re.I)


def planificar(pregunta: str, equipo: str | None) -> list[str]:
    """Plan determinista y auditable; nunca usa el LLM para conceder permisos."""
    texto = pregunta.strip()
    plan = ["consulta"]
    if _DIAGNOSTICO.search(texto) or (equipo is None and _ESTADO_GENERAL.search(texto)):
        plan.append("diagnostico")
    if _REPORTE.search(texto):
        plan.append("reporte")
    # Una consulta general debe contrastar estados; una pregunta de equipo puede resolverse solo con consulta.
    if equipo is None and "diagnostico" not in plan:
        plan.append("diagnostico")
    return plan


def herramientas_del_rol(rol: AgenteRol, herramientas: list[tuple[str, object]]) -> list[tuple[str, object]]:
    """Filtra por el nombre MCP sin el prefijo de equipo."""
    return [(alias, tool) for alias, tool in herramientas if rol.permite(tool.name)]

