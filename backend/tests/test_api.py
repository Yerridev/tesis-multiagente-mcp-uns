"""Pruebas del contrato HTTP con el frontend.

Verifican lo que el frontend React da por hecho:

* el JSON sale en **camelCase**;
* los **enums son strings** con el nombre exacto (``Confirmado``, ``Iniciar``…);
* los **errores** son ``{"error": "..."}`` (nunca ``{"detail": ...}``);
* las fechas son **ISO-8601 con offset** (las entiende ``new Date()``);
* el canal de telemetría es **SSE** (``/api/stream``).
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import cargar_config
from app.main import crear_app


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    cfg = cargar_config()
    cfg.auth.habilitado = False          # sin base de datos: la puerta queda abierta
    app = crear_app(cfg)
    with TestClient(app) as c:
        yield c


# ============================================================ salud
def test_health_devuelve_el_contrato_esperado(cliente):
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "healthy"
    assert cuerpo["service"] == "MCP Industrial API"
    datetime.fromisoformat(cuerpo["timestamp"])      # ISO-8601 parseable


def test_health_live_y_ready(cliente):
    assert cliente.get("/health/live").status_code == 200
    # ready puede ser 503 si no hay broker: lo importante es que responde JSON
    respuesta = cliente.get("/health/ready")
    assert respuesta.status_code in (200, 503)
    assert "checks" in respuesta.json()


# ============================================================ planta
def test_equipment_devuelve_los_cuatro_equipos_en_camelcase(cliente):
    respuesta = cliente.get("/api/equipment")
    assert respuesta.status_code == 200
    equipos = respuesta.json()
    assert {e["id"] for e in equipos} == {"nivel-mcn09", "caudal-mcc09",
                                          "presion-mcp09", "temp-mct09"}
    for equipo in equipos:
        # campos derivados que el frontend lee
        assert isinstance(equipo["status"], str)
        assert isinstance(equipo["deviation"], (int, float))
        assert isinstance(equipo["alarm"], bool)
        assert equipo["calidad"] in {"buena", "sensor_fuera_de_rango", "sin_calidad"}
        # ninguna clave en snake_case
        assert not any("_" in clave for clave in equipo), equipo


def test_senales_de_cada_modulo(cliente):
    for equipo in ("nivel-mcn09", "caudal-mcc09", "presion-mcp09", "temp-mct09"):
        respuesta = cliente.get(f"/api/equipment/{equipo}/signals")
        assert respuesta.status_code == 200, equipo
        cuerpo = respuesta.json()
        assert "mqtt" in cuerpo and "temaBase" in cuerpo and "valores" in cuerpo


def test_ruta_literal_de_signals_no_la_se_traga_la_de_equipo(cliente):
    """/api/equipment/nivel-mcn09/signals debe ganar a /api/equipment/{id}."""
    respuesta = cliente.get("/api/equipment/nivel-mcn09/signals")
    assert respuesta.status_code == 200
    assert "temaBase" in respuesta.json()


def test_detalle_de_nivel(cliente):
    respuesta = cliente.get("/api/equipment/nivel-mcn09/detail")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["equipmentId"] == "nivel-mcn09"
    assert "plcIp" in cuerpo and "tankHeight" in cuerpo and "vfdHz" in cuerpo


def test_equipment_inexistente_da_404(cliente):
    respuesta = cliente.get("/api/equipment/no-existe")
    assert respuesta.status_code == 404
    assert "error" in respuesta.json()


def test_history_devuelve_lista(cliente):
    respuesta = cliente.get("/api/history?limit=600")
    assert respuesta.status_code == 200
    assert isinstance(respuesta.json(), list)


def test_latencia(cliente):
    respuesta = cliente.get("/api/latencia")
    assert respuesta.status_code == 200
    assert "modulos" in respuesta.json()
    assert cliente.post("/api/latencia/reiniciar").json() == {"ok": True}


# ============================================================ errores
def test_los_errores_usan_el_campo_error_no_detail(cliente):
    """Los rechazos de caudal/presión/temperatura vuelven {"error": ...} (nunca detail)."""
    respuesta = cliente.post("/api/control/caudal/comandos",
                            json={"tipo": "Iniciar", "equipo": "caudal-mcc09"},
                            headers={"Authorization": "Bearer dev-supervisor"})
    assert respuesta.status_code in (400, 409)
    cuerpo = respuesta.json()
    assert "error" in cuerpo
    assert "detail" not in cuerpo


def test_el_rechazo_de_nivel_devuelve_la_orden_con_el_motivo(cliente):
    """El MCN-09 devuelve la ORDEN (con estado y motivo), igual que el backend .NET."""
    respuesta = cliente.post("/api/control/nivel/comandos",
                            json={"tipo": "Iniciar", "equipo": "presion-mcp09"},
                            headers={"Authorization": "Bearer dev-supervisor"})
    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "Rechazado"
    assert cuerpo["motivo"] == "EQUIPO_INVALIDO"
    assert cuerpo["id"]
    # las fechas van en ISO-8601 con offset (las entiende new Date())
    datetime.fromisoformat(cuerpo["expedida"])


def test_cuerpo_invalido_da_400_con_error(cliente):
    respuesta = cliente.post("/api/control/nivel/comandos",
                            json={"tipo": 12345},
                            headers={"Authorization": "Bearer dev-supervisor"})
    assert respuesta.status_code == 400
    assert "error" in respuesta.json()


# ============================================================ control
def test_estado_de_control_con_clave_de_desarrollo(cliente):
    respuesta = cliente.get("/api/control/estado",
                            headers={"Authorization": "Bearer dev-supervisor"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["usuario"] == "dev-supervisor"
    datos = cuerpo["datos"]
    assert datos["modoEfectivo"] in {"REAL", "DRY-RUN"}
    assert isinstance(datos["realArmado"], bool)
    assert isinstance(datos["motivosReal"], list)
    assert "proceso" in datos and "telemetria" in datos
    assert datos["proceso"]["mqttNivel"] in (True, False)


def test_control_sin_credencial_da_401(cliente):
    respuesta = cliente.get("/api/control/estado")
    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "SIN_AUTENTICACION"


def test_viewer_no_puede_escribir(cliente):
    respuesta = cliente.post("/api/control/nivel/comandos",
                            json={"tipo": "Iniciar", "equipo": "nivel-mcn09"},
                            headers={"Authorization": "Bearer dev-viewer"})
    assert respuesta.status_code == 403
    assert respuesta.json()["motivo"] == "PERMISO_INSUFICIENTE"


def test_contrato_de_control(cliente):
    respuesta = cliente.get("/api/control/contrato",
                            headers={"Authorization": "Bearer dev-supervisor"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["equipo"] == "nivel-mcn09"
    assert cuerpo["topicos"]["cmd"].endswith("/cmd")
    assert "O:0/*" in cuerpo["salidasProhibidas"]
    assert cuerpo["allowlist"]
    for direccion in cuerpo["allowlist"]:
        assert not direccion["direccion"].upper().startswith(("O:0", "O:1"))


def test_estados_de_los_otros_modulos(cliente):
    for clave in ("caudal", "presion", "temperatura"):
        respuesta = cliente.get(f"/api/control/{clave}/estado",
                                headers={"Authorization": "Bearer dev-supervisor"})
        assert respuesta.status_code == 200, clave
        datos = respuesta.json()["datos"]
        assert datos["modoEfectivo"] in {"REAL", "BLOQUEADO"}
        assert "proceso" in datos and "telemetria" in datos


# ============================================================ agente
def test_agent_status(cliente):
    respuesta = cliente.get("/api/agent/status")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["mode"] in {"llm", "rules"}
    assert cuerpo["provider"] == "OpenRouter"
    assert "multiagente" in cuerpo
    assert isinstance(cuerpo["models"], list)


def test_agent_tools(cliente):
    respuesta = cliente.get("/api/agent/tools")
    assert respuesta.status_code == 200
    assert len(respuesta.json()) == 5


def test_agent_ask_responde_con_reglas_sin_clave(cliente):
    respuesta = cliente.post("/api/agent/ask", json={"message": "estado de la planta"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert isinstance(cuerpo["reply"], str) and cuerpo["reply"]
    assert cuerpo["mode"] in {"llm", "rules", "multiagente"}
    assert isinstance(cuerpo["tools"], list)
    assert "conversacionId" in cuerpo
    datetime.fromisoformat(cuerpo["ts"])


def test_catalogo_mcp(cliente):
    respuesta = cliente.get("/api/mcp/catalogo")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert "disponible" in cuerpo
    assert "catalogo" in cuerpo


def test_conversaciones(cliente):
    respuesta = cliente.get("/api/agent/conversaciones")
    assert respuesta.status_code == 200
    assert isinstance(respuesta.json(), list)


# ============================================================ auth (deshabilitado)
def test_auth_estado_informa_que_esta_deshabilitado(cliente):
    respuesta = cliente.get("/api/auth/estado")
    assert respuesta.status_code == 200
    assert respuesta.json()["habilitado"] is False


def test_auth_yo_devuelve_el_modo_local(cliente):
    respuesta = cliente.get("/api/auth/yo")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["habilitado"] is False
    assert cuerpo["rol"] == "admin"


def test_listar_usuarios_sin_auth_da_409(cliente):
    respuesta = cliente.get("/api/auth/usuarios")
    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "AUTENTICACION_DESHABILITADA"


# ============================================================ lienzo
def test_lienzo_layout_404_si_no_existe(cliente):
    respuesta = cliente.get("/api/lienzo/nivel-mcn09/layout")
    assert respuesta.status_code in (200, 404)


def test_lienzo_put_valida_el_json(cliente):
    respuesta = cliente.put("/api/lienzo/nivel-mcn09/layout", content="no-json",
                            headers={"Content-Type": "application/json"})
    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "JSON_INVALIDO"


def test_lienzo_id_invalido(cliente):
    respuesta = cliente.get("/api/lienzo/AB/layout")
    assert respuesta.status_code == 400


# ============================================================ planta simulada
def test_planta_modo(cliente):
    respuesta = cliente.get("/api/planta/modo")
    assert respuesta.status_code == 200
    assert respuesta.json()["modo"] in {"real", "simulado"}


# ============================================================ SSE
@pytest.mark.asyncio
async def test_el_canal_sse_formatea_los_eventos_como_espera_el_front():
    """Un evento SSE es:  event: <nombre>\\ndata: <json>\\n\\n"""
    from app.stream.canal import CanalSSE, generar_stream

    canal = CanalSSE()
    cola = await canal.suscribir()
    await canal.emitir("telemetry", [{"id": "nivel-mcn09", "value": 12.3}])
    await canal.emitir("controlResultado", {"id": "abc", "estado": "Confirmado"})

    generador = generar_stream(cola)
    primero = await generador.__anext__()
    assert primero.startswith(b": ")            # comentario de apertura

    evento = await generador.__anext__()
    assert evento.startswith(b"event: telemetry\ndata: ")
    assert evento.endswith(b"\n\n")
    cuerpo = json.loads(evento.decode().split("data: ", 1)[1].strip())
    assert cuerpo[0]["id"] == "nivel-mcn09"

    evento2 = await generador.__anext__()
    assert evento2.startswith(b"event: controlResultado\ndata: ")
    assert b"Confirmado" in evento2

    await generador.aclose()
    await canal.desuscribir(cola)


@pytest.mark.asyncio
async def test_el_canal_sse_difunde_a_todos_los_clientes():
    from app.stream.canal import CanalSSE

    canal = CanalSSE()
    cola_a = await canal.suscribir()
    cola_b = await canal.suscribir()
    assert canal.clientes == 2

    await canal.emitir("nivelSenales", {"mqtt": True})
    assert (await cola_a.get())[0] == "nivelSenales"
    assert (await cola_b.get())[0] == "nivelSenales"

    await canal.desuscribir(cola_a)
    assert canal.clientes == 1


@pytest.mark.asyncio
async def test_el_stream_declara_las_cabeceras_correctas():
    """El endpoint SSE: content-type, no-cache y sin buffer (nginx)."""
    from starlette.requests import Request

    from app.main import crear_app

    cfg = cargar_config()
    cfg.auth.habilitado = False
    app = crear_app(cfg)

    scope = {
        "type": "http", "method": "GET", "path": "/api/stream", "headers": [],
        "query_string": b"", "app": app, "client": ("127.0.0.1", 1234),
        "scheme": "http", "server": ("test", 80), "root_path": "",
    }
    from app.main import stream as _stream

    respuesta = await _stream(Request(scope))
    assert respuesta.media_type == "text/event-stream"
    assert respuesta.headers["cache-control"].startswith("no-cache")
    assert respuesta.headers["x-accel-buffering"] == "no"
    await respuesta.body_iterator.aclose()
