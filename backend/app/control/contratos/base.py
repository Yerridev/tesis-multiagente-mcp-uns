"""Base de los contratos de control de caudal, presión y temperatura.

Los tres comparten estructura (triple gate, preflight, ack, timeouts) pero
tienen reglas propias: unidades, rangos, condiciones de bloqueo y señales
propias del módulo.  El de nivel (MCN-09) tiene un servicio aparte porque su
contrato es mucho más rico (allowlist, guard de calidad, propietario del mando).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from ...modelos import EstadoComando, TipoComando
from ..contrato import ControlContrato, Motivos
from ..servicio import OrdenControl, _bool_de

log = logging.getLogger(__name__)


class ControlModulo:
    """Contrato de control de un módulo (caudal / presión / temperatura)."""

    clave: str = ""
    equipo: str = ""
    unidad: str = ""
    telemetria_max_segundos: int = 15
    evento_resultado: str = "controlResultado"
    #: Tipos que este módulo admite.
    tipos_admitidos: frozenset = frozenset()
    #: Clave de MqttCfg con el broker donde se publican SUS órdenes.
    #: El conector de control de cada módulo puede vivir en otro broker
    #: (p. ej. el de la VM de presión), así que no es el mismo que el de telemetría.
    host_config: str = ""
    port_config: str = ""

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.cfg = getattr(ctx.cfg, f"control_{self.clave}")
        self.estado = ctx.estados[self.equipo]
        self._ordenes: dict[str, OrdenControl] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ helpers
    @property
    def topico_base(self) -> str:
        return self.cfg.topico_base

    def real_armado(self) -> bool:
        """Triple gate: configuración Real + escritura habilitada + variable de entorno."""
        return (self.cfg.modo.lower() == "real"
                and self.cfg.habilitado_escritura
                and self.cfg.variable_entorno_real == "1")

    def _edad_telemetria(self) -> float | None:
        ultimo = self.estado.ultimo_mensaje
        if ultimo is None:
            return None
        return (datetime.now().astimezone() - ultimo).total_seconds()

    # ------------------------------------------------------------------ contrato
    def validar(self, solicitud, tipo: TipoComando) -> str | None:
        """Devuelve el motivo de error si la orden no cumple el contrato."""
        raise NotImplementedError

    def preflight(self, solicitud, tipo: TipoComando) -> str | None:
        """Condiciones del proceso. Devuelve el motivo de bloqueo o None."""
        raise NotImplementedError

    def proceso_publico(self) -> dict[str, Any]:
        raise NotImplementedError

    # ------------------------------------------------------------------ envío
    async def enviar(self, solicitud, usuario: str, rol: str) -> tuple[int, OrdenControl | None, str | None]:
        # Instancia de SOLO LECTURA: no se publica nada en MQTT.
        if not self.ctx.cfg.control.publicar:
            return 409, None, Motivos.PUBLICACION_DESHABILITADA

        if (solicitud.equipo or "").lower() != self.equipo.lower():
            return 400, None, Motivos.EQUIPO_INVALIDO

        tipo = ControlContrato.parsear_tipo(solicitud.tipo)
        if tipo is None or tipo not in self.tipos_admitidos:
            return 400, None, Motivos.TIPO_DESCONOCIDO

        if not ControlContrato.rol_suficiente(rol, tipo):
            return 403, None, Motivos.PERMISO_INSUFICIENTE

        invalido = self.validar(solicitud, tipo)
        if invalido is not None:
            return 400, None, invalido

        bloqueante = self.preflight(solicitud, tipo)
        if bloqueante is not None:
            return 409, None, bloqueante

        ahora = datetime.now().astimezone()
        orden = OrdenControl(
            id=uuid.uuid4().hex,
            tipo=tipo,
            valor=solicitud.valor,
            parametro=(solicitud.parametro or "").lower() or None,
            unidad=solicitud.unidad,
            equipo=self.equipo,
            comentario=solicitud.comentario,
            correlacion=solicitud.correlacion,
            origen=solicitud.origen,
            usuario=usuario,
            rol=rol,
            modo="REAL",
            expedida=ahora,
            expira=ahora + timedelta(seconds=self.cfg.expiracion_segundos),
            timeout_en=ahora + timedelta(seconds=self.cfg.timeout_segundos),
            estado=EstadoComando.enviado,
            actualizada=ahora,
        )
        async with self._lock:
            self._ordenes[orden.id] = orden

        cuerpo = json.dumps(orden.para_senal(), ensure_ascii=False, default=str)
        if not await self._publicar(cuerpo):
            orden.estado = EstadoComando.error
            orden.motivo = Motivos.MQTT_NO_DISPONIBLE
            return 503, orden, orden.motivo

        await self._difundir(orden)
        return 202, orden, None

    async def _publicar(self, cuerpo: str) -> bool:
        from ...mqtt.publicador import publicar

        return await publicar(f"{self.topico_base}/cmd", cuerpo,
                              self._host_control(), self._puerto_control())

    def _host_control(self) -> str:
        """Broker donde se publican las órdenes de ESTE módulo.

        Por defecto es el broker de telemetría; cada módulo puede tener el suyo
        (``Mqtt__CaudalControlHost``, ``Mqtt__PresionControlHost``…).
        """
        host = getattr(self.ctx.cfg.mqtt, self.host_config, None) if self.host_config else None
        return host or self.ctx.cfg.mqtt.host

    def _puerto_control(self) -> int:
        puerto = getattr(self.ctx.cfg.mqtt, self.port_config, None) if self.port_config else None
        return puerto or self.ctx.cfg.mqtt.port

    async def _difundir(self, orden: OrdenControl) -> None:
        try:
            await self.ctx.canal.emitir(self.evento_resultado, orden.para_senal())
        except Exception:                       # pragma: no cover
            log.debug("No se pudo difundir la orden %s", orden.id)

    # ------------------------------------------------------------------ estado
    def estado_publico(self) -> dict[str, Any]:
        edad = self._edad_telemetria()
        return {
            "modoEfectivo": "REAL" if self.real_armado() else "BLOQUEADO",
            "realArmado": self.real_armado(),
            "proceso": self.proceso_publico(),
            "telemetria": {
                "ultimo": self.estado.ultimo_mensaje,
                "edadSegundos": round(edad, 1) if edad is not None else None,
                "fresca": (edad is not None and edad <= self.telemetria_max_segundos),
                "maxSegundos": self.telemetria_max_segundos,
            },
            "pendientes": sum(1 for o in self._ordenes.values() if not o.es_terminal),
        }

    def ultimas(self, limite: int = 10) -> list[dict[str, Any]]:
        limite = max(1, min(50, limite if limite and limite > 0 else 10))
        ordenados = sorted(self._ordenes.values(), key=lambda o: o.expedida, reverse=True)
        return [o.para_senal() for o in ordenados[:limite]]

    # ------------------------------------------------------------------ ack
    def procesar_ack(self, texto: str) -> None:
        """Procesa el ack del conector (``{Topico}/ack``)."""
        try:
            raiz = json.loads(texto)
        except ValueError:
            return
        if not isinstance(raiz, dict):
            return
        orden = self._ordenes.get(raiz.get("id") or "")
        if orden is None or orden.es_terminal:
            return

        estado_txt = str(raiz.get("estado") or "")
        try:
            nuevo = EstadoComando(estado_txt)
        except ValueError:
            try:
                nuevo = EstadoComando(estado_txt.lower())
            except ValueError:
                return
        orden.estado = nuevo
        orden.actualizada = datetime.now().astimezone()
        orden.motivo = raiz.get("motivo")
        escrito = _bool_de(raiz.get("escrito"))
        if escrito is not None:
            orden.escrito = escrito
        for campo in ("valor_leido", "valor_esperado"):
            valor = raiz.get(campo)
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                setattr(orden, campo, float(valor))
        asyncio.get_running_loop().create_task(self._difundir(orden))

    def verificar_timeouts(self) -> None:
        ahora = datetime.now().astimezone()
        for orden in self._ordenes.values():
            if orden.es_terminal or ahora < orden.timeout_en:
                continue
            orden.estado = EstadoComando.timeout
            orden.motivo = Motivos.SIN_CONFIRMACION
            orden.actualizada = ahora

    # ------------------------------------------------------------------ MQTT
    async def consumir(self) -> None:
        """Suscribe a ``{Topico}/ack`` y barre los timeouts."""
        from ...mqtt.suscriptor import consumir_topico

        async def _barrer() -> None:
            while True:
                try:
                    await asyncio.sleep(1.0)
                    self.verificar_timeouts()
                except asyncio.CancelledError:
                    raise
                except Exception:               # pragma: no cover
                    log.exception("Fallo el barrido de timeouts")

        tarea = asyncio.create_task(_barrer(), name=f"control-{self.clave}-timeouts")
        try:
            await consumir_topico(
                self.ctx,
                f"{self.topico_base}/ack",
                lambda _t, cuerpo: self.procesar_ack(cuerpo),
                cliente_id=f"mcp-control-{self.clave}",
                host=self.ctx.cfg.mqtt.host,
                puerto=self.ctx.cfg.mqtt.port,
            )
        finally:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
