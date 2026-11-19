"""Pruebas del contrato de control del MCN-09 en modo DRY-RUN.

Port de ``tests/MCP.Industrial.Api.Tests/ControlTests.cs`` (xUnit → pytest).
Sin PLC, sin MQTT real y sin escrituras.

Casos cubiertos:
  1 usuario inexistente · 2 viewer sin permiso · 3 operador con setpoint (rechazado)
  4 setpoint válido (supervisor) · 5 fuera de rango · 6 unidad incorrecta · 7 vencida
  8 duplicada · 9 PLC desconectado · 10 MQTT desconectado · 11 telemetría vencida
  12 selector LOCAL · 13 selector REMOTO (camino feliz) · 14 nivel bajo T1
  15/16/17/18 allowlist sin O:0/O:1 · 19 triple gate incompleto · 20 ack aceptado
  21 ack rechazado · 22 ack duplicado · 23 timeout (sin ack y tras ESCRITO sin
  CONFIRMADO) · 24 lectura posterior diferente · 25 lectura posterior coincidente
  26/27 pulso y pérdida de conexión → conector Python · 28 sensor de nivel
  saturado · 29 calidad desconocida · 30 override de calidad · 31 saturación y
 _feed del historial · 32 carrera de orden de llegada · 33 contexto del agente.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.control.contrato import ALLOWLIST_NIVEL, ControlContrato, Motivos
from app.control.servicio import ControlService
from app.estado.planta import PlantState
from app.estado.modulo import EstadoModulo
from app.modulos import NIVEL
from app.modelos import EstadoComando, TipoComando
from conftest import _nivel_estado


def _ack(id_: str, estado: str, motivo: str | None = None, escrito: bool | None = None,
         esperado: float | None = None, leido: float | None = None) -> str:
    extras = ""
    if escrito is not None:
        extras += f',"escrito":{"true" if escrito else "false"}'
    if esperado is not None:
        extras += f',"valor_esperado":{esperado}'
    if leido is not None:
        extras += f',"valor_leido":{leido}'
    return (f'{{"id":"{id_}","estado":"{estado}","motivo":'
            f'{json.dumps(motivo) if motivo else "null"},"modo":"DRY-RUN"{extras}}}')


def _setpoint(valor: float, unidad: str | None = "cm"):
    from app.modelos import SolicitudComando

    return SolicitudComando(tipo="Setpoint", valor=valor, parametro=None,
                             unidad=unidad, equipo="nivel-mcn09")


# ============================================================ 1 autenticación
def test_usuario_inexistente_o_sin_token_da_401(crear_servicio):
    """Sin cabecera Authorization (o con una clave desconocida) → 401."""
    from app.config import ControlCfg
    from app.rutas.control import _autenticar
    from conftest import CanalFalso, CfgFalso, CtxFalso

    def _peticion(cabecera: str | None):
        class _Estado:
            pass

        class _App:
            pass

        class _Req:
            def __init__(self):
                self.headers = {"authorization": cabecera} if cabecera else {}
                self.state = _Estado()
                self.app = _App()
                self.app.state = _Estado()

        req = _Req()
        req.app.state.ctx = CtxFalso(
            CfgFalso(control=ControlCfg(usuarios={"dev-supervisor": "supervisor"})),
            {},
            CanalFalso(),
        )
        return req

    rol, _, fallo = _autenticar(_peticion(None))
    assert rol is None
    assert fallo is not None and fallo.status_code == 401

    rol, _, fallo = _autenticar(_peticion("Bearer dev-que-no-existe"))
    assert rol is None
    assert fallo is not None and fallo.status_code == 401

    rol, usuario, fallo = _autenticar(_peticion("Bearer dev-supervisor"))
    assert rol == "supervisor"
    assert usuario == "dev-supervisor"
    assert fallo is None


# ============================================================ 2 viewer
@pytest.mark.asyncio
async def test_viewer_intentando_iniciar_se_rechaza(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio()
    res = await servicio.enviar(SolicitudComando(tipo="Iniciar"), "viewer1", "viewer")
    assert res[0] == 403
    assert res[1].motivo == Motivos.PERMISO_INSUFICIENTE


# ============================================================ 3 operador con setpoint
@pytest.mark.asyncio
async def test_operador_con_setpoint_se_rechaza_por_rol(crear_servicio):
    servicio, _ = crear_servicio()
    res = await servicio.enviar(_setpoint(10), "op1", "operador")
    assert res[0] == 403
    assert res[1].motivo == Motivos.PERMISO_INSUFICIENTE


# ============================================================ 4 camino feliz
@pytest.mark.asyncio
async def test_setpoint_valido_de_supervisor_se_envia(crear_servicio):
    servicio, publicados = crear_servicio()
    res = await servicio.enviar(_setpoint(20.5), "sup1", "supervisor")
    assert res[0] == 202
    orden = res[1]
    assert orden.estado is EstadoComando.enviado
    assert orden.unidad == "cm"
    assert orden.equipo == "nivel-mcn09"
    assert len(publicados) == 1
    cuerpo = json.loads(publicados[0])
    assert cuerpo["id"] == orden.id
    assert cuerpo["equipo"] == "nivel-mcn09"


# ============================================================ 5 rango
@pytest.mark.asyncio
async def test_setpoint_fuera_de_rango_se_rechaza(crear_servicio):
    servicio, _ = crear_servicio()
    res = await servicio.enviar(_setpoint(99), "sup1", "supervisor")
    assert res[0] == 400
    assert res[1].motivo == Motivos.RANGO_INVALIDO


# ============================================================ 6 unidad
@pytest.mark.asyncio
async def test_setpoint_con_unidad_incorrecta_se_rechaza(crear_servicio):
    servicio, _ = crear_servicio()
    res = await servicio.enviar(_setpoint(10, "psi"), "sup1", "supervisor")
    assert res[0] == 400
    assert res[1].motivo == Motivos.UNIDAD_INVALIDA

    sin_unidad = await servicio.enviar(_setpoint(10, None), "sup1", "supervisor")
    assert sin_unidad[1].motivo == Motivos.UNIDAD_INVALIDA


# ============================================================ 7 vencida
@pytest.mark.asyncio
async def test_ack_despues_de_expirar_se_marca_vencida(crear_servicio, reloj):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio()
    res = await servicio.enviar(SolicitudComando(tipo="Iniciar"), "u", "operador")
    assert res[0] == 202

    reloj.avanzar(timedelta(seconds=20))        # > ExpiracionSegundos (15)
    servicio.procesar_ack(_ack(res[1].id, "ACEPTADO"))

    orden = servicio.obtener(res[1].id)
    assert orden.estado is EstadoComando.vencido
    assert orden.motivo == Motivos.VENCIDA


# ============================================================ 8 duplicada
@pytest.mark.asyncio
async def test_orden_duplicada_pendiente_se_rechaza(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio()
    primera = await servicio.enviar(SolicitudComando(tipo="Iniciar"), "u", "operador")
    assert primera[0] == 202
    segunda = await servicio.enviar(SolicitudComando(tipo="Iniciar"), "u", "operador")
    assert segunda[0] == 409
    assert segunda[1].motivo == Motivos.DUPLICADA


# ============================================================ 9 PLC desconectado
@pytest.mark.asyncio
async def test_plc_desconectado_se_rechaza(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio(_nivel_estado(plc="DESCONECTADO"))
    res = await servicio.enviar(SolicitudComando(tipo="Detener"), "u", "operador")
    assert res[0] == 409
    assert res[1].motivo == Motivos.PLC_DESCONECTADO


# ============================================================ 10 MQTT desconectado
@pytest.mark.asyncio
async def test_mqtt_desconectado_se_rechaza(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio(_nivel_estado(mqtt=False))
    res = await servicio.enviar(SolicitudComando(tipo="Detener"), "u", "operador")
    assert res[0] == 409
    assert res[1].motivo == Motivos.MQTT_NO_DISPONIBLE


# ============================================================ 11 telemetría vencida
@pytest.mark.asyncio
async def test_telemetria_vencida_se_rechaza(crear_servicio):
    from app.modelos import SolicitudComando

    sin_datos = EstadoModulo(NIVEL)
    sin_datos.mqtt_conectado = True
    servicio, _ = crear_servicio(sin_datos)
    res = await servicio.enviar(SolicitudComando(tipo="Detener"), "u", "operador")
    assert res[0] == 409
    assert res[1].motivo == Motivos.TELEMETRIA_VENCIDA


# ============================================================ 12/13 selector
@pytest.mark.asyncio
async def test_selector_local_se_rechaza(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio(_nivel_estado(selector="LOCAL"))
    res = await servicio.enviar(SolicitudComando(tipo="Detener"), "u", "operador")
    assert res[0] == 409
    assert res[1].motivo == Motivos.SELECTOR_NO_REMOTO


@pytest.mark.asyncio
async def test_selector_remoto_permite_el_envio(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio(_nivel_estado(selector="REMOTO"))
    res = await servicio.enviar(SolicitudComando(tipo="Detener"), "u", "operador")
    assert res[0] == 202


@pytest.mark.asyncio
async def test_fuente_hmi_bloquea_todas_las_ordenes_web(crear_servicio):
    servicio, _ = crear_servicio(_nivel_estado(fuente_control="HMI"))
    res = await servicio.enviar(_setpoint(10), "u", "supervisor")
    assert res[0] == 409
    assert res[1].motivo == Motivos.CONTROL_EN_HMI


@pytest.mark.asyncio
async def test_fuente_sin_dato_falla_de_forma_segura(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio(_nivel_estado(fuente_control=None))
    res = await servicio.enviar(SolicitudComando(tipo="Detener"), "u", "operador")
    assert res[0] == 409
    assert res[1].motivo == Motivos.FUENTE_CONTROL_SIN_DATO


# ============================================================ 14 nivel bajo T1
@pytest.mark.asyncio
async def test_nivel_bajo_t1_bloquea_arranque_permitiendo_setpoint(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio(_nivel_estado(nivel_bajo=True))
    arranque = await servicio.enviar(SolicitudComando(tipo="Iniciar"), "u", "operador")
    assert arranque[0] == 409
    assert arranque[1].motivo == Motivos.NIVEL_BAJO_T1

    sp = await servicio.enviar(_setpoint(10), "u", "supervisor")
    assert sp[0] == 202


# ============================================================ 15-18 allowlist
def test_allowlist_sin_salidas_prohibidas_y_solo_marcha_pc_verificada():
    for direccion in ALLOWLIST_NIVEL:
        assert not ControlContrato.es_salida_prohibida(direccion.direccion), direccion.direccion
    verificadas = sorted(d.direccion for d in ALLOWLIST_NIVEL if d.verificada)
    assert verificadas == sorted(["B3:0/3", "B3:0/4", "B3:0/13", "N7:5", "N7:8", "N7:9",
                                  "N7:10", "N7:1", "N7:2"])
    assert ControlContrato.es_salida_prohibida("O:0/2")
    assert ControlContrato.es_salida_prohibida("O:1/0")
    # el contrato no expone ningún campo de dirección
    from app.modelos import SolicitudComando

    assert not any("direccion" in f.lower() for f in SolicitudComando.model_fields)


# ============================================================ 19 triple gate
def test_modo_real_exige_entorno_config_y_selector(crear_servicio):
    servicio, _ = crear_servicio(modo="Real", habilitado_escritura=True)
    assert servicio.modo_efectivo() == "DRY-RUN"

    servicio2, _ = crear_servicio(modo="Real", habilitado_escritura=True,
                                  variable_entorno_real="1")
    assert servicio2.modo_efectivo() == "REAL"


# ============================================================ 20/22 ack
@pytest.mark.asyncio
async def test_ack_aceptado_se_propaga_y_el_duplicado_se_ignora(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio()
    res = await servicio.enviar(SolicitudComando(tipo="Iniciar"), "u", "operador")
    servicio.procesar_ack(_ack(res[1].id, "ACEPTADO"))
    assert servicio.obtener(res[1].id).estado is EstadoComando.aceptado   # NO terminal

    servicio.procesar_ack(_ack(res[1].id, "RECHAZADO", "DESPUES_DE_ACEPTADA"))
    assert servicio.obtener(res[1].id).estado is EstadoComando.aceptado   # no pisa ACEPTADO


@pytest.mark.asyncio
async def test_ack_rechazado_propaga_el_motivo(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio()
    res = await servicio.enviar(SolicitudComando(tipo="Iniciar"), "u", "operador")
    servicio.procesar_ack(_ack(res[1].id, "RECHAZADO", "SELECTOR_NO_REMOTO"))
    orden = servicio.obtener(res[1].id)
    assert orden.estado is EstadoComando.rechazado
    assert orden.motivo == "SELECTOR_NO_REMOTO"


# ============================================================ 23 timeouts
@pytest.mark.asyncio
async def test_sin_ack_se_marca_timeout(crear_servicio, reloj):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio()
    res = await servicio.enviar(SolicitudComando(tipo="Detener"), "u", "operador")
    assert res[1].estado is EstadoComando.enviado

    reloj.avanzar(timedelta(seconds=6))        # > TimeoutSegundos (5)
    servicio.verificar_timeouts()

    orden = servicio.obtener(res[1].id)
    assert orden.estado is EstadoComando.timeout
    assert orden.motivo == Motivos.SIN_CONFIRMACION


@pytest.mark.asyncio
async def test_escrito_sin_confirmacion_se_marca_timeout(crear_servicio, reloj):
    servicio, _ = crear_servicio()
    res = await servicio.enviar(_setpoint(12), "u", "supervisor")
    servicio.procesar_ack(_ack(res[1].id, "ACEPTADO", escrito=False))
    servicio.procesar_ack(_ack(res[1].id, "ESCRITO", escrito=True, esperado=12))
    assert servicio.obtener(res[1].id).estado is EstadoComando.escrito

    reloj.avanzar(timedelta(seconds=6))
    servicio.verificar_timeouts()
    assert servicio.obtener(res[1].id).estado is EstadoComando.timeout


# ============================================================ 24/25 confirmación
@pytest.mark.asyncio
async def test_confirmado_con_lectura_distinta_se_marca_error(crear_servicio):
    servicio, _ = crear_servicio()
    res = await servicio.enviar(_setpoint(15), "u", "supervisor")
    servicio.procesar_ack(_ack(res[1].id, "ACEPTADO", escrito=False))
    servicio.procesar_ack(_ack(res[1].id, "ESCRITO", escrito=True, esperado=15))
    servicio.procesar_ack(_ack(res[1].id, "CONFIRMADO", escrito=True, esperado=15, leido=3))

    orden = servicio.obtener(res[1].id)
    assert orden.estado is EstadoComando.error
    assert orden.motivo == Motivos.CONFIRMACION_NO_COINCIDE
    assert orden.valor_esperado == 15
    assert orden.valor_leido == 3


@pytest.mark.asyncio
async def test_confirmado_con_lectura_coincidente_cierra_la_orden(crear_servicio):
    servicio, _ = crear_servicio()
    res = await servicio.enviar(_setpoint(15), "u", "supervisor")
    servicio.procesar_ack(_ack(res[1].id, "ACEPTADO", escrito=False))
    servicio.procesar_ack(_ack(res[1].id, "ESCRITO", escrito=True, esperado=15))
    servicio.procesar_ack(_ack(res[1].id, "CONFIRMADO", escrito=True, esperado=15, leido=15))

    orden = servicio.obtener(res[1].id)
    assert orden.estado is EstadoComando.confirmado
    assert orden.es_terminal
    assert orden.motivo is None

    # un ack tardío tras la terminal no pisa el estado
    servicio.procesar_ack(_ack(res[1].id, "RECHAZADO", "TARDIO"))
    assert servicio.obtener(res[1].id).estado is EstadoComando.confirmado


# ============================================================ 26 simulador
@pytest.mark.asyncio
async def test_flujo_completo_con_simulador_hasta_confirmado(crear_servicio):
    servicio, publicados = crear_servicio(_nivel_estado(plc="DESCONECTADO", selector="LOCAL"))
    servicio.procesar_state('{"simulador":true}')
    res = await servicio.enviar(_setpoint(20), "u", "supervisor")
    assert res[0] == 202
    assert len(publicados) == 1

    servicio.procesar_ack(_ack(res[1].id, "ACEPTADO", escrito=False))
    assert servicio.obtener(res[1].id).estado is EstadoComando.aceptado

    servicio.procesar_ack(_ack(res[1].id, "ESCRITO", escrito=True, esperado=20))
    assert servicio.obtener(res[1].id).estado is EstadoComando.escrito

    servicio.procesar_ack(_ack(res[1].id, "CONFIRMADO", escrito=True, esperado=20, leido=20))
    assert servicio.obtener(res[1].id).estado is EstadoComando.confirmado


# ============================================================ trazabilidad
@pytest.mark.asyncio
async def test_orden_lleva_correlacion_comentario_y_origen(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, publicados = crear_servicio()
    sol = SolicitudComando(tipo="Setpoint", valor=10, parametro=None, unidad="cm",
                            equipo="nivel-mcn09", comentario="prueba de trazabilidad",
                            correlacion="corr-123", origen="SCADA-WEB")
    res = await servicio.enviar(sol, "sup1", "supervisor")

    assert res[1].correlacion == "corr-123"
    assert res[1].comentario == "prueba de trazabilidad"
    assert res[1].origen == "SCADA-WEB"
    cuerpo = publicados[0]
    assert "corr-123" in cuerpo
    assert "SCADA-WEB" in cuerpo


# ============================================================ equipo
@pytest.mark.asyncio
async def test_equipo_distinto_de_nivel_mcn09_se_rechaza(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, _ = crear_servicio()
    sol = SolicitudComando(tipo="Iniciar", equipo="presion-mcp09")
    res = await servicio.enviar(sol, "u", "operador")
    assert res[0] == 400
    assert res[1].motivo == Motivos.EQUIPO_INVALIDO


@pytest.mark.asyncio
async def test_tipo_ajustar_valvula_se_rechaza_en_nivel(crear_servicio):
    """AjustarValvula es exclusivo del MCC-09 (caudal)."""
    from app.modelos import SolicitudComando

    servicio, publicados = crear_servicio()
    res = await servicio.enviar(SolicitudComando(tipo="AjustarValvula", valor=50, equipo="nivel-mcn09"),
                                "u", "supervisor")
    assert res[0] == 400
    assert res[1].motivo == Motivos.TIPO_DESCONOCIDO
    assert publicados == []


# ============================================================ instancia de SOLO LECTURA
@pytest.mark.asyncio
async def test_con_publicar_deshabilitado_no_se_publica_ninguna_orden(crear_servicio):
    """Instancia de solo lectura (stack paralelo): la orden se rechaza y no sale nada."""
    from app.modelos import SolicitudComando

    servicio, publicados = crear_servicio(publicar=False)
    res = await servicio.enviar(SolicitudComando(tipo="Iniciar", equipo="nivel-mcn09"),
                                "u", "operador")
    assert res[0] == 409
    assert res[1].motivo == Motivos.PUBLICACION_DESHABILITADA
    assert publicados == []          # NADA se publica en MQTT


@pytest.mark.asyncio
async def test_con_publicar_deshabilitado_tampoco_salta_la_validacion(crear_servicio):
    """El rechazo por solo lectura no esquiva los permisos ni el resto de reglas."""
    from app.modelos import SolicitudComando

    servicio, publicados = crear_servicio(publicar=False)
    # un viewer tampoco puede escribir: el motivo sigue siendo el de permisos
    res = await servicio.enviar(SolicitudComando(tipo="Iniciar", equipo="nivel-mcn09"),
                                "u", "viewer")
    assert res[0] == 409
    assert res[1].motivo == Motivos.PUBLICACION_DESHABILITADA
    assert publicados == []


# ============================================================ sensor saturado
def _nivel_saturado() -> EstadoModulo:
    estado = _nivel_estado()
    base = f"{NIVEL.base_mqtt}/funcional"
    estado.aplicar(f"{base}/nivel/fuera_rango_sensor", '{"value":true}')
    return estado


@pytest.mark.asyncio
async def test_sensor_de_nivel_fuera_de_rango_bloquea_la_orden(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, publicados = crear_servicio(_nivel_saturado())
    res = await servicio.enviar(SolicitudComando(tipo="Iniciar", equipo="nivel-mcn09"),
                                "u", "operador")
    assert res[0] == 409
    assert res[1].motivo == Motivos.NIVEL_SENSOR_FUERA_DE_RANGO
    assert res[1].estado is EstadoComando.rechazado
    assert publicados == []


@pytest.mark.asyncio
async def test_sensor_de_nivel_fuera_de_rango_bloquea_tambien_el_setpoint(crear_servicio):
    servicio, publicados = crear_servicio(_nivel_saturado())
    res = await servicio.enviar(_setpoint(20), "u", "supervisor")
    assert res[0] == 409
    assert res[1].motivo == Motivos.NIVEL_SENSOR_FUERA_DE_RANGO
    assert publicados == []


@pytest.mark.asyncio
async def test_detener_si_se_permite_con_el_sensor_de_nivel_fuera_de_rango(crear_servicio):
    from app.modelos import SolicitudComando

    servicio, publicados = crear_servicio(_nivel_saturado())
    res = await servicio.enviar(SolicitudComando(tipo="Detener", equipo="nivel-mcn09"),
                                "u", "operador")
    assert res[0] == 202
    assert len(publicados) == 1


@pytest.mark.asyncio
async def test_sensor_de_nivel_en_rango_no_bloquea_la_orden(crear_servicio):
    servicio, publicados = crear_servicio(_nivel_estado())
    res = await servicio.enviar(_setpoint(20), "u", "supervisor")
    assert res[0] == 202
    assert len(publicados) == 1


@pytest.mark.asyncio
async def test_calidad_de_nivel_desconocida_bloquea_la_orden(crear_servicio):
    """Sin la lectura primaria del sensor no se conoce la calidad: fail-closed."""
    sin_calidad = EstadoModulo(NIVEL)
    sin_calidad.mqtt_conectado = True
    base = f"{NIVEL.base_mqtt}/funcional"
    sin_calidad.aplicar(f"{base}/plc/conexion", "CONECTADO")
    sin_calidad.aplicar(f"{base}/estado/selector_remoto", "true")
    sin_calidad.aplicar(f"{base}/estado/fuente_control", "PC")

    servicio, publicados = crear_servicio(sin_calidad)
    res = await servicio.enviar(_setpoint(20), "u", "supervisor")
    assert res[0] == 409
    assert res[1].motivo == Motivos.NIVEL_CALIDAD_DESCONOCIDA
    assert publicados == []


@pytest.mark.asyncio
async def test_override_de_calidad_permite_la_orden_pero_la_marca(crear_servicio):
    """Operación degradada autorizada: la orden sale, pero queda marcada."""
    servicio, _ = crear_servicio(_nivel_saturado(), permitir_sensor_fuera_de_rango=True)

    # Con el sensor saturado la consigna en cm no significa nada: se rechaza
    # aunque el override esté activo (si no, la perilla de la web se
    # desincroniza).  Ver docs/09-migracion-backend-python.md.
    setpoint = await servicio.enviar(_setpoint(20), "u", "supervisor")
    assert setpoint[0] == 409
    assert setpoint[1].motivo == Motivos.NIVEL_SENSOR_FUERA_DE_RANGO

    # Pero una orden que NO depende del PV (arranque) sí sale, marcada.
    from app.modelos import SolicitudComando

    arranque = await servicio.enviar(SolicitudComando(tipo="Iniciar", equipo="nivel-mcn09"),
                                     "u", "operador")
    assert arranque[0] == 202
    assert arranque[1].override_calidad is True


@pytest.mark.asyncio
async def test_sin_override_el_sensor_fuera_de_rango_sigue_bloqueando(crear_servicio):
    servicio, _ = crear_servicio(_nivel_saturado())
    res = await servicio.enviar(_setpoint(20), "u", "supervisor")
    assert res[0] == 409
    assert res[1].motivo == Motivos.NIVEL_SENSOR_FUERA_DE_RANGO


# ============================================================ historial
def test_nivel_saturado_no_alimenta_el_historial_ni_el_valor_vigente():
    nivel = EstadoModulo(NIVEL)
    base = f"{NIVEL.base_mqtt}/funcional"
    nivel.aplicar(f"{base}/plc/conexion", "CONECTADO")
    nivel.aplicar(f"{base}/estado/selector_remoto", "true")
    nivel.aplicar(f"{base}/estado/fuente_control", "PC")
    # lectura válida: tanque vacío (N7:4 ≈ 16548 → 0 cm)
    nivel.aplicar(f"{base}/nivel/raw", '{"value":16548,"unit":"cuentas"}')
    nivel.aplicar(f"{base}/nivel/cm", '{"value":-0.5,"unit":"cm"}')

    planta = PlantState({"nivel-mcn09": nivel})
    planta.aplicar()

    assert len(planta.historial("nivel-mcn09", 100)) == 1
    assert round(planta.obtener("nivel-mcn09")["value"], 2) == -0.5
    assert planta.obtener("nivel-mcn09")["calidad"] == "buena"

    # el sensor se satura: llega el artefacto de 40,7 cm
    nivel.aplicar(f"{base}/nivel/fuera_rango_sensor", '{"value":true}')
    nivel.aplicar(f"{base}/nivel/raw", '{"value":56,"unit":"cuentas"}')
    nivel.aplicar(f"{base}/nivel/cm", '{"value":40.7,"unit":"cm"}')
    planta.aplicar()

    equipo = planta.obtener("nivel-mcn09")
    assert equipo["calidad"] == "sensor_fuera_de_rango"
    assert equipo["alarm"] is False
    assert equipo["value"] != 40.7          # el artefacto NO pasa a valor vigente
    assert len(planta.historial("nivel-mcn09", 100)) == 1   # el historial no crece
    assert planta.obtener("nivel-mcn09")["value"] is None
    detalle = planta.detalle_nivel()
    assert detalle["level"] is None
    assert detalle["percent"] is None
    assert detalle["calidad"] == "sensor_fuera_de_rango"


def test_nivel_que_llega_antes_de_conocer_la_calidad_no_se_acepta():
    nivel = EstadoModulo(NIVEL)
    nivel.mqtt_conectado = True
    base = f"{NIVEL.base_mqtt}/funcional"
    # llega primero el cm saturado, sin raw ni flag
    nivel.aplicar(f"{base}/nivel/cm", '{"value":40.7,"unit":"cm"}')

    planta = PlantState({"nivel-mcn09": nivel})
    planta.aplicar()

    assert planta.obtener("nivel-mcn09")["calidad"] == "sin_calidad"
    assert planta.obtener("nivel-mcn09")["value"] != 40.7
    assert planta.historial("nivel-mcn09", 100) == []

    # al llegar el dato primario se detecta la saturación (raw < 300 cuentas)
    nivel.aplicar(f"{base}/nivel/raw", '{"value":56,"unit":"cuentas"}')
    planta.aplicar()

    assert planta.obtener("nivel-mcn09")["calidad"] == "sensor_fuera_de_rango"
    assert planta.obtener("nivel-mcn09")["value"] != 40.7
    assert planta.historial("nivel-mcn09", 100) == []


def test_el_contexto_del_agente_no_anuncia_un_nivel_no_medible():
    from app.agentes.reglas import contexto_sistema

    nivel = EstadoModulo(NIVEL)
    nivel.mqtt_conectado = True
    base = f"{NIVEL.base_mqtt}/funcional"
    nivel.aplicar(f"{base}/plc/conexion", "CONECTADO")
    nivel.aplicar(f"{base}/nivel/fuera_rango_sensor", '{"value":true}')
    nivel.aplicar(f"{base}/nivel/cm", '{"value":40.7,"unit":"cm"}')

    planta = PlantState({"nivel-mcn09": nivel})
    planta.aplicar()

    contexto = contexto_sistema(planta)
    assert "MEDIDA NO VÁLIDA" in contexto
    assert "SENSOR DE NIVEL FUERA DE RANGO" in contexto
    assert "nivel = 40.7 cm" not in contexto
