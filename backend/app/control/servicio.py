"""Servicio de control remoto del nivel MCN-09.

Port de ``Control/ControlService.cs``.  El backend **NUNCA** escribe al PLC:
solo valida, audita y publica la orden en MQTT (``.../control/cmd``); la
escritura real la hace el conector Python tras su propio triple gate.

Ciclo de vida de una orden::

    Recibido -> Validando -> Enviado -> (ack) Aceptado -> Escrito -> Confirmado

Terminales: ``Confirmado | Rechazado | Vencido | Timeout | Error``.

``ACEPTADO`` = el conector recibió la orden.  ``ESCRITO`` = el conector ejecutó
la escritura (solo modo real).  ``CONFIRMADO`` = una **lectura posterior**
coincide con el valor esperado: nunca se marca por la simple entrega MQTT.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..modelos import EstadoComando, TipoComando
from .auditoria import ControlAuditoria
from .contrato import (
    ALLOWLIST_NIVEL,
    ESTADOS_FINALES,
    TODOS_MOTIVOS,
    ControlContrato,
    Motivos,
)

log = logging.getLogger(__name__)


@dataclass
class OrdenControl:
    """Orden de control rastreada por su id único. Trazabilidad completa."""

    id: str
    tipo: TipoComando
    equipo: str
    usuario: str
    rol: str
    modo: str
    expedida: datetime
    expira: datetime
    timeout_en: datetime
    valor: float | None = None
    parametro: str | None = None
    unidad: str | None = None
    comentario: str | None = None
    correlacion: str | None = None
    origen: str | None = None
    estado: EstadoComando = EstadoComando.recibido
    motivo: str | None = None
    actualizada: datetime | None = None
    valor_esperado: float | None = None
    valor_leido: float | None = None
    escrito: bool | None = None
    override_calidad: bool = False

    @property
    def es_terminal(self) -> bool:
        return self.estado in ESTADOS_FINALES

    def para_senal(self) -> dict[str, Any]:
        """Representación pública (la que ve el frontend y va por SSE).

        Las fechas salen en ISO-8601 con offset, tal como las emitía el backend
        .NET: es lo que ``new Date(...)`` del navegador entiende.
        """
        return {
            "id": self.id,
            "tipo": self.tipo.value,
            "valor": self.valor,
            "parametro": self.parametro,
            "unidad": self.unidad,
            "equipo": self.equipo,
            "comentario": self.comentario,
            "correlacion": self.correlacion,
            "origen": self.origen,
            "usuario": self.usuario,
            "rol": self.rol,
            "modo": self.modo,
            "estado": self.estado.value,
            "motivo": self.motivo,
            "expedida": self.expedida.isoformat(),
            "expira": self.expira.isoformat(),
            "timeoutEn": self.timeout_en.isoformat(),
            "actualizada": self.actualizada.isoformat() if self.actualizada else None,
            "escrito": self.escrito,
            "valorEsperado": self.valor_esperado,
            "valorLeido": self.valor_leido,
            "overrideCalidad": self.override_calidad,
        }


class ControlService:
    """Orquestador de control remoto del nivel-mcn09."""

    def __init__(self, ctx, publicar=None, ahora=None) -> None:
        self.ctx = ctx
        self.cfg = ctx.cfg.control
        self.nivel = ctx.estados["nivel-mcn09"]
        self.auditoria = ControlAuditoria(self.cfg.auditoria_ruta)
        self._ordenes: dict[str, OrdenControl] = {}
        self._lock = asyncio.Lock()
        self._conector_simulador = False
        #: Reloj inyectable (pruebas: para expirar y vencer órdenes).
        self._ahora = ahora or (lambda: datetime.now().astimezone())
        #: Transporte alternativo (pruebas: se publica en memoria, sin broker).
        self._publicar_fn = publicar

    # ------------------------------------------------------------------ triple gate
    def evaluar_modo_real(self) -> tuple[bool, list[str]]:
        """Solo con los tres interruptores (entorno + configuración + selector
        REMOTO) queda armado el modo REAL."""
        motivos: list[str] = []
        if self.cfg.modo.lower() != "real":
            motivos.append("MODO_CONFIG_NO_REAL")
        if not self.cfg.habilitado_escritura:
            motivos.append("ESCRITURA_NO_HABILITADA")
        if self.cfg.variable_entorno_real != "1":
            motivos.append("CONTROL_REAL_NO_DEFINIDO")
        if not self._conector_simulador and self.nivel.modo() != "REMOTO":
            motivos.append(Motivos.SELECTOR_NO_REMOTO)
        return (not motivos, motivos)

    def modo_efectivo(self) -> str:
        return "REAL" if self.evaluar_modo_real()[0] else "DRY-RUN"

    # ------------------------------------------------------------------ estado público
    def estado_publico(self) -> dict[str, Any]:
        armado, motivos = self.evaluar_modo_real()
        ultimo = None if self._conector_simulador else self.nivel.ultimo_mensaje
        edad = None if ultimo is None else round((self._ahora() - ultimo).total_seconds(), 1)
        fresca = bool(self._conector_simulador or (edad is not None and edad <= ControlContrato.TELEMETRIA_MAX_SEGUNDOS))
        return {
            "modoEfectivo": self.modo_efectivo(),
            "realArmado": armado,
            "motivosReal": motivos,
            "configuracion": {
                "modo": self.cfg.modo,
                "habilitadoEscritura": self.cfg.habilitado_escritura,
                "controlReal": self.cfg.variable_entorno_real,
                "timeoutSegundos": self.cfg.timeout_segundos,
                "expiracionSegundos": self.cfg.expiracion_segundos,
            },
            "proceso": {
                "simulador": self._conector_simulador,
                "plc": "SIMULADOR" if self._conector_simulador
                       else ("CONECTADO" if self.nivel.plc_conectado else "DESCONECTADO"),
                "selector": "SIMULADOR" if self._conector_simulador else self.nivel.modo(),
                "nivelBajoT1": False if self._conector_simulador
                              else self.nivel.booleano("estado/alarma_nivel_bajo_tanque1"),
                "mqttNivel": self.nivel.mqtt_conectado,
                # Propietario del mando (B3:0/3): "PC" = SCADA web · "HMI" = HMI físico.
                "fuenteControl": "SIMULADOR" if self._conector_simulador
                                 else self.nivel.fuente_control(),
                # El sensor de nivel saturado invalida la medida del lazo.
                "sensorSaturado": False if self._conector_simulador else self.nivel.sensor_saturado,
                # Operación degradada autorizada: el guard de calidad está anulado.
                "overrideCalidad": self.cfg.permitir_sensor_fuera_de_rango,
            },
            "telemetria": {
                "ultimo": ultimo,
                "edadSegundos": edad,
                "fresca": fresca,
                "maxSegundos": ControlContrato.TELEMETRIA_MAX_SEGUNDOS,
            },
            "pendientes": sum(1 for o in self._ordenes.values() if not o.es_terminal),
        }

    def contrato_publico(self) -> dict[str, Any]:
        base = self.cfg.topico_base
        return {
            "equipo": ControlContrato.EQUIPO,
            "topicos": {"cmd": f"{base}/cmd", "ack": f"{base}/ack", "state": f"{base}/state"},
            "tipos": [
                {"tipo": "Iniciar", "valor": None, "rango": None, "rolMinimo": "operador"},
                {"tipo": "Detener", "valor": None, "rango": None, "rolMinimo": "operador"},
                {"tipo": "Reiniciar", "valor": None, "rango": None, "rolMinimo": "operador"},
                {"tipo": "Setpoint", "valor": "cm",
                 "rango": [ControlContrato.SETPOINT_MIN, ControlContrato.SETPOINT_MAX],
                 "rolMinimo": "supervisor"},
                {"tipo": "ParametroPid", "valor": "kp|ti|td",
                 "rango": "kp 0-50 · ti 0-600 · td 0-60", "rolMinimo": "supervisor"},
                {"tipo": "AbrirValvula", "valor": None, "rango": None, "rolMinimo": "supervisor"},
                {"tipo": "CerrarValvula", "valor": None, "rango": None, "rolMinimo": "supervisor"},
            ],
            "estados": [e.value for e in EstadoComando],
            "confirmacion": {
                "regla": "CONFIRMADO exige una lectura posterior del PLC que coincida con el valor "
                         "esperado; la entrega MQTT por sí sola nunca confirma.",
                "distincion": "ACEPTADO = conector recibió · ESCRITO = conector ejecutó la escritura "
                              "· CONFIRMADO = lectura posterior coincide",
            },
            "motivos": TODOS_MOTIVOS,
            "salidasProhibidas": ["O:0/*", "O:1/*"],
            "allowlist": [
                {"tag": d.tag, "direccion": d.direccion, "tipo": d.tipo, "uso": d.uso,
                 "verificada": d.verificada,
                 "estado": "VERIFICADA" if d.verificada else "NO_VERIFICADAS"}
                for d in ALLOWLIST_NIVEL
            ],
            "estado": self.estado_publico(),
        }

    # ------------------------------------------------------------------ envío
    async def enviar(self, solicitud, usuario: str, rol: str) -> tuple[int, OrdenControl | None, str | None]:
        """Valida, audita y publica la orden. Devuelve (http, orden, error)."""
        ahora = self._ahora()

        # 0* instancia de SOLO LECTURA: no se publica nada en MQTT.
        if not self.cfg.publicar:
            orden = self._nueva(solicitud, TipoComando.iniciar, ahora,
                                 ControlContrato.EQUIPO, usuario, rol)
            return self._rechazar(orden, Motivos.PUBLICACION_DESHABILITADA, 409)

        # 0* equipo exacto (solo nivel-mcn09; vacío = nivel-mcn09 por compatibilidad con la SPA)
        equipo = (solicitud.equipo or "").strip() or ControlContrato.EQUIPO
        if equipo.lower() != ControlContrato.EQUIPO.lower():
            orden = self._nueva(solicitud, TipoComando.iniciar, ahora, equipo, usuario, rol)
            return self._rechazar(orden, Motivos.EQUIPO_INVALIDO, 400)

        tipo = ControlContrato.parsear_tipo(solicitud.tipo)
        if tipo is None:
            orden = self._nueva(solicitud, TipoComando.iniciar, ahora, equipo, usuario, rol)
            return self._rechazar(orden, Motivos.TIPO_DESCONOCIDO, 400)

        orden = self._nueva(solicitud, tipo, ahora, equipo, usuario, rol)
        orden.estado = EstadoComando.validando

        # 1* permisos por rol
        if not ControlContrato.rol_suficiente(rol, tipo):
            return self._rechazar(orden, Motivos.PERMISO_INSUFICIENTE, 403)

        # 2* unidad obligatoria para Setpoint (cm)
        if tipo is TipoComando.setpoint and (solicitud.unidad or "").strip().lower() != ControlContrato.UNIDAD_SETPOINT:
            return self._rechazar(orden, Motivos.UNIDAD_INVALIDA, 400)

        # 3* rango del valor / parámetro PID
        error_valor = (ControlContrato.validar_pid(solicitud.parametro, solicitud.valor)
                       if tipo is TipoComando.parametro_pid
                       else ControlContrato.validar_valor(tipo, solicitud.valor))
        if error_valor is not None:
            return self._rechazar(orden, error_valor, 400)

        # 4* duplicados: no dos órdenes idénticas pendientes a la vez
        async with self._lock:
            duplicada = any(
                not o.es_terminal
                and o.tipo == tipo
                and o.valor == orden.valor
                and (o.parametro or "").lower() == (orden.parametro or "").lower()
                and (ahora - o.expedida).total_seconds() <= self.cfg.ventana_duplicados_segundos
                for o in self._ordenes.values()
            )
        if duplicada:
            return self._rechazar(orden, Motivos.DUPLICADA, 409)

        # Setpoint con el sensor de nivel saturado: la consigna en cm no significa nada
        # (el PID recorta PV y consigna al mismo valor -> error 0 -> salida 0) y la
        # perilla de la web se desincroniza.
        # DECISIÓN DE MIGRACIÓN: se rechaza SIEMPRE, también con el override de calidad
        # activo.  Con la medida del sensor saturada, mandar una consigna en cm al lazo
        # sería pilotar contra un PV ficticio; el override solo habilita órdenes que no
        # dependen del PV (arranque, parada, válvula).  Ver docs/09-migracion-backend-python.md.
        if tipo is TipoComando.setpoint and self.nivel.sensor_saturado:
            return self._rechazar(orden, Motivos.NIVEL_SENSOR_FUERA_DE_RANGO, 409)

        # 5* preflight del proceso (mismo criterio en dry-run y real; el conector
        #    simulador lo saltea)
        if not self._conector_simulador:
            if not self.nivel.mqtt_conectado:
                return self._rechazar(orden, Motivos.MQTT_NO_DISPONIBLE, 409)

            # telemetría fresca: sin dato reciente del edge no se expide ninguna orden
            ultimo = self.nivel.ultimo_mensaje
            edad = None if ultimo is None else (self._ahora() - ultimo).total_seconds()
            if edad is None or edad > ControlContrato.TELEMETRIA_MAX_SEGUNDOS:
                return self._rechazar(orden, Motivos.TELEMETRIA_VENCIDA, 409)

            if not self.cfg.permitir_sensor_fuera_de_rango:
                # PotenciaVariador es una orden MANUAL explícita del operador (no un
                # lazo automático): no se bloquea por la calidad del sensor.
                manual = tipo in (TipoComando.detener, TipoComando.potencia_variador)
                if self.nivel.sensor_saturado and not manual:
                    return self._rechazar(orden, Motivos.NIVEL_SENSOR_FUERA_DE_RANGO, 409)
                # Sin calidad conocida del dato de nivel tampoco se mueve el proceso.
                if not self.nivel.calidad_conocida and not manual:
                    return self._rechazar(orden, Motivos.NIVEL_CALIDAD_DESCONOCIDA, 409)
            elif self.nivel.sensor_saturado or not self.nivel.calidad_conocida:
                # Operación degradada autorizada: la orden sale, pero marcada.
                orden.override_calidad = True

            if not self.nivel.plc_conectado:
                return self._rechazar(orden, Motivos.PLC_DESCONECTADO, 409)

            if self.nivel.modo() != "REMOTO":
                return self._rechazar(orden, Motivos.SELECTOR_NO_REMOTO, 409)

            # B3:0/3 arbitra el propietario: 0=PC/web, 1=HMI. Sin dato también se
            # bloquea (fail closed). El backend jamás cambia este bit.
            fuente = self.nivel.fuente_control()
            if fuente is None:
                return self._rechazar(orden, Motivos.FUENTE_CONTROL_SIN_DATO, 409)
            if fuente == "HMI":
                return self._rechazar(orden, Motivos.CONTROL_EN_HMI, 409)

            if tipo is TipoComando.iniciar and self.nivel.booleano("estado/alarma_nivel_bajo_tanque1") is True:
                return self._rechazar(orden, Motivos.NIVEL_BAJO_T1, 409)

        # 6* publicar la orden (el backend jamás escribe al PLC)
        async with self._lock:
            self._ordenes[orden.id] = orden
        cuerpo = self._serializar_orden(orden, self.nivel.sensor_saturado)
        publicado = await self._publicar(cuerpo)
        if not publicado:
            if orden.estado in (EstadoComando.recibido, EstadoComando.validando):
                orden.estado = EstadoComando.error
                orden.motivo = Motivos.MQTT_NO_DISPONIBLE
                orden.actualizada = self._ahora()
                self._finalizar(orden, "PUBLICACION_FALLIDA")
            return 503, orden, Motivos.MQTT_NO_DISPONIBLE

        # El conector puede responder mientras se publica (ack más rápido que esta
        # continuación): solo marcamos ENVIADO si nadie ya cerró/avanzó la orden.
        if orden.estado in (EstadoComando.recibido, EstadoComando.validando):
            orden.estado = EstadoComando.enviado
            orden.actualizada = self._ahora()

        self.auditoria.registrar(
            "ENVIO", orden.id, usuario, rol, orden.estado.value,
            f"{orden.tipo.value} {orden.valor} {orden.unidad} {orden.parametro} "
            f"modo={orden.modo} correlacion={orden.correlacion} comentario={orden.comentario}"
            + (" [OVERRIDE: sensor de nivel fuera de rango — operación degradada autorizada]"
               if orden.override_calidad else ""),
        )
        await self._difundir(orden)
        log.info("Orden %s %s publicada (%s) por %s; estado actual %s",
                 orden.id, orden.tipo.value, orden.modo, usuario, orden.estado.value)
        return 202, orden, None

    # ------------------------------------------------------------------ helpers
    def _nueva(self, solicitud, tipo: TipoComando, ahora: datetime, equipo: str,
               usuario: str, rol: str) -> OrdenControl:
        return OrdenControl(
            id=uuid.uuid4().hex[:16],
            tipo=tipo,
            valor=solicitud.valor,
            parametro=solicitud.parametro,
            unidad=solicitud.unidad,
            equipo=equipo,
            comentario=solicitud.comentario,
            correlacion=solicitud.correlacion,
            origen=solicitud.origen,
            usuario=usuario,
            rol=rol,
            modo=self.modo_efectivo(),
            expedida=ahora,
            expira=ahora + timedelta(seconds=self.cfg.expiracion_segundos),
            timeout_en=ahora + timedelta(seconds=self.cfg.timeout_segundos),
        )

    def _rechazar(self, orden: OrdenControl, motivo: str, codigo: int) -> tuple[int, OrdenControl, str]:
        orden.estado = EstadoComando.rechazado
        orden.motivo = motivo
        orden.actualizada = self._ahora()
        self._ordenes[orden.id] = orden
        self._finalizar(orden, "VALIDACION")
        return codigo, orden, motivo

    def _finalizar(self, orden: OrdenControl, accion: str) -> None:
        self.auditoria.registrar(accion, orden.id, orden.usuario, orden.rol,
                                 orden.estado.value, orden.motivo)
        try:
            asyncio.get_running_loop().create_task(self._difundir(orden))
        except RuntimeError:
            pass        # sin bucle activo (p. ej. pruebas unitarias síncronas)

    async def _difundir(self, orden: OrdenControl) -> None:
        try:
            await self.ctx.canal.emitir("controlResultado", orden.para_senal())
        except Exception:                       # pragma: no cover
            log.debug("No se pudo difundir la orden %s", orden.id)

    def _serializar_orden(self, orden: OrdenControl, sensor_saturado: bool) -> str:
        return json.dumps({
            "id": orden.id,
            "equipo": orden.equipo,
            "tipo": orden.tipo.value,
            "parametro": orden.parametro,
            "valor": orden.valor,
            "unidad": orden.unidad or (ControlContrato.UNIDAD_SETPOINT
                                       if orden.tipo is TipoComando.setpoint else None),
            "comentario": orden.comentario,
            "correlacion": orden.correlacion,
            "origen": orden.origen,
            "expedida": orden.expedida.isoformat(),
            "expira": orden.expira.isoformat(),
            "modo": orden.modo,
            # El conector decide el modo de arranque con esto (no depende de su suscripción).
            "sensorSaturado": sensor_saturado,
            "origenOrden": {"usuario": orden.usuario, "rol": orden.rol},
        }, ensure_ascii=False)

    async def _publicar(self, cuerpo: str) -> bool:
        if self._publicar_fn is not None:
            return await self._publicar_fn(cuerpo)
        from ..mqtt.publicador import publicar

        return await publicar(f"{self.cfg.topico_base}/cmd", cuerpo,
                              self.ctx.cfg.mqtt.host, self.ctx.cfg.mqtt.port)

    # ------------------------------------------------------------------ ack / state
    def procesar_ack(self, texto: str) -> None:
        """Procesa el ack del conector Python (``{Topico}/ack``)."""
        try:
            raiz = json.loads(texto)
        except ValueError:
            log.warning("Ack de control ilegible")
            return
        if not isinstance(raiz, dict):
            return

        id_ = raiz.get("id")
        orden = self._ordenes.get(id_) if id_ else None
        if orden is None or orden.es_terminal:
            return          # ack duplicado de una terminal: se ignora

        estado_txt = str(raiz.get("estado") or "").upper()
        motivo = raiz.get("motivo")
        detalle = raiz.get("detalle")
        modo = raiz.get("modo")
        if isinstance(modo, str) and modo.upper() == "SIMULADOR":
            self._conector_simulador = True

        # rastro de escritura / lectura posterior
        escrito = _bool_de(raiz.get("escrito"))
        if escrito is not None:
            orden.escrito = escrito
        if isinstance(raiz.get("valor_esperado"), (int, float)) and not isinstance(
                raiz.get("valor_esperado"), bool):
            orden.valor_esperado = float(raiz["valor_esperado"])
        if isinstance(raiz.get("valor_leido"), (int, float)) and not isinstance(
                raiz.get("valor_leido"), bool):
            orden.valor_leido = float(raiz["valor_leido"])

        ahora = self._ahora()
        if ahora > orden.expira and estado_txt != "CONFIRMADO":
            orden.estado = EstadoComando.vencido
            orden.motivo = Motivos.VENCIDA
        else:
            if estado_txt == "ACEPTADO":
                orden.estado = EstadoComando.aceptado
                orden.motivo = None
            elif estado_txt == "ESCRITO":
                orden.estado = EstadoComando.escrito
                orden.motivo = None
                orden.escrito = True if orden.escrito is None else orden.escrito
            elif estado_txt == "CONFIRMADO":
                # Solo se confirma si la lectura posterior coincide con el esperado.
                if (orden.valor_esperado is not None and orden.valor_leido is not None
                        and abs(orden.valor_esperado - orden.valor_leido) > 1e-6):
                    orden.estado = EstadoComando.error
                    orden.motivo = Motivos.CONFIRMACION_NO_COINCIDE
                else:
                    orden.estado = EstadoComando.confirmado
                    orden.motivo = None
            elif estado_txt == "RECHAZADO":
                # una orden ya aceptada/escrita no retrocede por un ack tardío
                if orden.estado in (EstadoComando.aceptado, EstadoComando.escrito):
                    return
                orden.estado = EstadoComando.rechazado
                orden.motivo = motivo or "RECHAZADO_POR_CONECTOR"
            else:
                orden.estado = EstadoComando.error
                orden.motivo = motivo or "ACK_DESCONOCIDO"

        orden.actualizada = ahora
        self._finalizar(orden, "ACK")
        log.info("Ack orden %s: %s %s escrito=%s leido=%s %s",
                 orden.id, orden.estado.value, orden.motivo, orden.escrito,
                 orden.valor_leido, detalle)

    def procesar_state(self, texto: str) -> None:
        """Procesa el estado del conector (``{Topico}/state``)."""
        try:
            raiz = json.loads(texto)
        except ValueError:
            log.warning("State de control ilegible")
            return
        if isinstance(raiz, dict) and "simulador" in raiz:
            self._conector_simulador = _bool_de(raiz["simulador"]) is True

    # ------------------------------------------------------------------ timeouts
    def verificar_timeouts(self) -> None:
        """Marca TIMEOUT a las órdenes enviadas/aceptadas/escritas sin confirmación."""
        ahora = self._ahora()
        for orden in list(self._ordenes.values()):
            if orden.es_terminal:
                continue
            if orden.estado not in (EstadoComando.enviado, EstadoComando.aceptado,
                                    EstadoComando.escrito):
                continue
            if ahora < orden.timeout_en:
                continue
            previo = orden.estado
            orden.estado = EstadoComando.timeout
            orden.motivo = Motivos.SIN_CONFIRMACION
            orden.actualizada = ahora
            self._finalizar(orden, "TIMEOUT")
            log.warning("Orden %s sin confirmación (%s, estado previo %s)",
                        orden.id, orden.tipo.value, previo.value)

    # ------------------------------------------------------------------ consultas
    def obtener(self, id_: str) -> OrdenControl | None:
        return self._ordenes.get(id_)

    def ultimas(self, limite: int = 10) -> list[OrdenControl]:
        limite = max(1, min(200, limite if limite and limite > 0 else 10))
        return sorted(self._ordenes.values(), key=lambda o: o.expedida, reverse=True)[:limite]

    # ------------------------------------------------------------------ MQTT
    async def consumir(self) -> None:
        """Suscribe a ``.../ack`` y ``.../state`` y barre los timeouts."""
        from ..mqtt.suscriptor import consumir_topico

        async def _barrer() -> None:
            while True:
                try:
                    await asyncio.sleep(1.0)
                    self.verificar_timeouts()
                except asyncio.CancelledError:
                    raise
                except Exception:               # pragma: no cover
                    log.exception("Fallo el barrido de timeouts")

        tarea = asyncio.create_task(_barrer(), name="control-timeouts")
        try:
            await consumir_topico(
                self.ctx,
                f"{self.cfg.topico_base}/ack",
                lambda _t, cuerpo: self.procesar_ack(cuerpo),
                cliente_id=f"mcp-control-nivel-{self.ctx.cfg.mqtt.host}",
                host=self.ctx.cfg.mqtt.host,
                puerto=self.ctx.cfg.mqtt.port,
            )
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)


def _bool_de(valor: Any) -> bool | None:
    """Convierte a bool tolerando "true"/"false"/1/0 (nunca lanza)."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto in {"true", "1", "yes", "si"}:
            return True
        if texto in {"false", "0", "no"}:
            return False
    return None
