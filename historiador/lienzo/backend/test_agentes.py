import unittest

from agentes import AGENTES, herramientas_del_rol, planificar


class Tool:
    def __init__(self, name: str):
        self.name = name


class PlanificacionTest(unittest.TestCase):
    def test_consulta_de_equipo(self):
        self.assertEqual(planificar("¿Cuál es el nivel actual?", "nivel-mcn09"), ["consulta"])

    def test_diagnostico(self):
        self.assertEqual(
            planificar("¿Por qué la presión no sigue al setpoint?", "presion-mcp09"),
            ["consulta", "diagnostico"],
        )

    def test_reporte_general(self):
        self.assertEqual(
            planificar("Compara el histórico de todos los equipos", None),
            ["consulta", "diagnostico", "reporte"],
        )

    def test_listas_blancas(self):
        tools = [("nivel", Tool("obtener_lectura")), ("nivel", Tool("diagnosticar_nivel")),
                 ("nivel", Tool("consultar_grafo"))]
        consulta = [t.name for _, t in herramientas_del_rol(AGENTES["consulta"], tools)]
        diagnostico = [t.name for _, t in herramientas_del_rol(AGENTES["diagnostico"], tools)]
        self.assertEqual(consulta, ["obtener_lectura"])
        self.assertEqual(diagnostico, ["obtener_lectura", "diagnosticar_nivel", "consultar_grafo"])
        self.assertEqual(AGENTES["coordinador"].herramientas, ())


if __name__ == "__main__":
    unittest.main()
