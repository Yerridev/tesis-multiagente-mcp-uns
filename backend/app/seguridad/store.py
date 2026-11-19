"""Autenticación: usuarios, sesiones e historial de accesses (TimescaleDB).

Port de ``Auth/Seguridad.cs``.  Detalles que se conservan:

* contraseñas **PBKDF2-SHA256** con 210 000 iteraciones y sal aleatoria; el
  formato guardado (``pbkdf2-sha256$iteraciones$salt_b64$hash_b64``) es
  byte-compatible con el de .NET, así que las cuentas existentes siguen
  entrando sin cambiar la contraseña;
* sesiones con token aleatorio de 256 bits; en la base solo se guarda su
  SHA-256;
* máximo 5 intentos fallidos por usuario+IP cada 10 minutos;
* la primera cuenta administradora sale del entorno
  (``ADMIN_USUARIO`` / ``ADMIN_PASSWORD``), nunca del código.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg

from ..config import AuthCfg

log = logging.getLogger(__name__)

ITERACIONES = 210_000
CACHE_SESION_S = 30
MAX_INTENTOS = 5
VENTANA_BLOQUEO_MIN = 10

ROLES = ("viewer", "operador", "supervisor", "admin")

USUARIO_VALIDO = re.compile(r"^[a-z0-9._-]{3,40}$")

ESQUEMA = """
CREATE SCHEMA IF NOT EXISTS seguridad;
CREATE TABLE IF NOT EXISTS seguridad.usuarios (
    id            serial PRIMARY KEY,
    usuario       text NOT NULL UNIQUE,
    nombre        text NOT NULL,
    rol           text NOT NULL CHECK (rol IN ('viewer','operador','supervisor','admin')),
    hash          text NOT NULL,
    activo        boolean NOT NULL DEFAULT true,
    creado        timestamptz NOT NULL DEFAULT now(),
    ultimo_acceso timestamptz
);
CREATE TABLE IF NOT EXISTS seguridad.sesiones (
    token_hash text PRIMARY KEY,
    usuario_id integer NOT NULL REFERENCES seguridad.usuarios(id),
    creada     timestamptz NOT NULL DEFAULT now(),
    expira     timestamptz NOT NULL,
    ip         text,
    agente     text,
    revocada   boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS seguridad.accesos (
    id      bigserial PRIMARY KEY,
    ts      timestamptz NOT NULL DEFAULT now(),
    usuario text NOT NULL,
    evento  text NOT NULL,
    ip      text,
    detalle text
);
CREATE INDEX IF NOT EXISTS accesos_ts_idx ON seguridad.accesos (ts DESC);
DELETE FROM seguridad.sesiones WHERE expira < now() - interval '7 days';
"""


def _ascii_seguro(texto: str, limite: int = 200) -> str:
    """Deja el texto en ASCII imprimible.

    Los mensajes de PostgreSQL vienen en UTF-8 y la consola de Windows usa
    cp1252: sin esto, un carácter no representable rompe el ``log`` (y con
    él, la tarea que estaba escribiendo).
    """
    return (texto or "").encode("ascii", errors="replace").decode("ascii")[:limite]


@dataclass
class SesionActiva:
    usuario_id: int
    usuario: str
    nombre: str
    rol: str
    expira: datetime


# --------------------------------------------------------------------------- hash
def hashear(password: str) -> str:
    """PBKDF2-SHA256 con sal aleatoria (mismo formato que el backend .NET)."""
    sal = secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sal, ITERACIONES, dklen=32)
    return "pbkdf2-sha256${}${}${}".format(
        ITERACIONES,
        base64.b64encode(sal).decode(),
        base64.b64encode(resumen).decode(),
    )


def verificar(password: str, guardado: str) -> bool:
    partes = guardado.split("$")
    if len(partes) != 4 or partes[0] != "pbkdf2-sha256":
        return False
    try:
        iteraciones = int(partes[1])
        sal = base64.b64decode(partes[2])
        esperado = base64.b64decode(partes[3])
    except (ValueError, TypeError):
        return False
    resumen = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sal, iteraciones,
                                  dklen=len(esperado))
    return hmac.compare_digest(resumen, esperado)


def validar_password(password: str | None) -> str | None:
    if not password or len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres"
    return None


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest().upper()


# --------------------------------------------------------------------------- store
class SeguridadStore:
    """Usuarios, sesiones y accesos en TimescaleDB (esquema ``seguridad``)."""

    def __init__(self, op: AuthCfg) -> None:
        self.op = op
        self.listo = False
        self.error_inicio: str | None = None
        self._cache: dict[str, tuple[SesionActiva, float]] = {}
        self._fallos: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ arranque
    async def inicializar(self) -> None:
        if not self.op.conexion:
            self.error_inicio = "sin cadena de conexión (Auth:Conexion)"
            return
        for intento in range(1, 31):
            try:
                await self._ejecutar(ESQUEMA)
                await self._sembrar_admin()
                self.listo = True
                self.error_inicio = None
                log.info("Seguridad lista (usuarios en TimescaleDB, esquema seguridad)")
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.error_inicio = _ascii_seguro(str(exc), 300)
                log.warning("Base de seguridad no disponible (%s); reintento %d/30 en 4 s",
                            _ascii_seguro(str(exc)), intento)
                await asyncio.sleep(4)
        self.listo = False

    def _dsn(self) -> str:
        """Convierte la cadena de conexión estilo Npgsql al formato libpq de psycopg."""
        dsn = (self.op.conexion or "").strip()
        if "://" in dsn or dsn.startswith("postgres"):
            return dsn
        equivalencia = {
            "host": "host", "server": "host", "port": "port", "database": "dbname",
            "username": "user", "user id": "user", "password": "password",
            "ssl mode": "sslmode", "trust server certificate": "sslmode",
        }
        partes = []
        for trozo in dsn.split(";"):
            if "=" not in trozo:
                continue
            clave, _, valor = trozo.partition("=")
            partes.append(f"{equivalencia.get(clave.strip().lower(), clave.strip().lower())}={valor.strip()}")
        return " ".join(partes)

    async def _ejecutar(self, sql: str, params: tuple = ()) -> None:
        dsn = self._dsn()
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)

    async def _consultar(self, sql: str, params: tuple = ()) -> list[tuple]:
        dsn = self._dsn()
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                if cur.description is None:
                    return []
                return await cur.fetchall()

    async def _sembrar_admin(self) -> None:
        filas = await self._consultar("SELECT count(*) FROM seguridad.usuarios")
        if filas and int(filas[0][0]) > 0:
            return
        usuario = (self.op.admin_usuario or "").strip().lower()
        if not usuario or not self.op.admin_password:
            log.warning("No hay usuarios y faltan ADMIN_USUARIO / ADMIN_PASSWORD en el .env: "
                        "nadie podrá entrar")
            return
        await self._ejecutar(
            "INSERT INTO seguridad.usuarios (usuario, nombre, rol, hash) VALUES (%s, %s, 'admin', %s)",
            (usuario, "Administrador", hashear(self.op.admin_password)),
        )
        await self.registrar(usuario, "usuario_creado", None, "admin inicial desde .env")
        log.info("Usuario administrador inicial creado: %s", usuario)

    # ------------------------------------------------------------------ sesiones
    def _bloqueado(self, clave: str) -> bool:
        fallos = self._fallos.get(clave)
        if not fallos:
            return False
        ahora = time.time()
        fallos[:] = [t for t in fallos if t > ahora - VENTANA_BLOQUEO_MIN * 60]
        return len(fallos) >= MAX_INTENTOS

    def _fallo(self, clave: str) -> None:
        self._fallos.setdefault(clave, []).append(time.time())

    async def login(self, usuario: str | None, password: str | None,
                    ip: str | None, agente: str | None) -> tuple[SesionActiva | None, str | None, str | None]:
        """Devuelve (sesión, token, error)."""
        u = (usuario or "").strip().lower()
        if not u or not password:
            return None, None, "CREDENCIALES_INCOMPLETAS"

        clave = f"{u}|{ip}"
        if self._bloqueado(clave):
            await self.registrar(u, "login_bloqueado", ip, "demasiados intentos")
            return None, None, "DEMASIADOS_INTENTOS"

        filas = await self._consultar(
            "SELECT id, nombre, rol, hash, activo FROM seguridad.usuarios WHERE usuario = %s", (u,)
        )
        if not filas:
            self._fallo(clave)
            await self.registrar(u, "login_fallido", ip, "usuario inexistente")
            return None, None, "CREDENCIALES_INVALIDAS"

        id_, nombre, rol, hash, activo = filas[0]
        if not verificar(password, hash):
            self._fallo(clave)
            await self.registrar(u, "login_fallido", ip, "contraseña incorrecta")
            return None, None, "CREDENCIALES_INVALIDAS"
        if not activo:
            await self.registrar(u, "login_fallido", ip, "usuario desactivado")
            return None, None, "USUARIO_DESACTIVADO"

        token = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        horas = max(1, min(72, self.op.horas_sesion))
        await self._ejecutar(
            """INSERT INTO seguridad.sesiones (token_hash, usuario_id, expira, ip, agente)
               VALUES (%s, %s, now() + make_interval(hours => %s), %s, %s)""",
            (_sha(token), id_, horas, ip, (agente or "")[:200] or None),
        )
        await self._ejecutar("UPDATE seguridad.usuarios SET ultimo_acceso = now() WHERE id = %s", (id_,))
        self._fallos.pop(clave, None)
        await self.registrar(u, "login_ok", ip, None)
        expira = datetime.now(timezone.utc) + timedelta(hours=horas)
        return SesionActiva(id_, u, nombre, rol, expira), token, None

    async def validar(self, token: str | None) -> SesionActiva | None:
        if not token:
            return None
        # Token de servicio (solo lectura) para el servidor MCP y las pruebas.
        servicio = self.op.token_servicio
        if servicio and len(servicio) >= 16 and hmac.compare_digest(token, servicio):
            return SesionActiva(0, "servicio-mcp", "Servicio MCP (solo lectura)", "viewer",
                                datetime.now(timezone.utc) + timedelta(hours=1))
        if not self.listo:
            return None

        h = _sha(token)
        ahora = time.time()
        cacheada = self._cache.get(h)
        if cacheada and cacheada[1] > ahora and cacheada[0].expira > datetime.now(timezone.utc):
            return cacheada[0]

        try:
            filas = await self._consultar(
                """SELECT u.id, u.usuario, u.nombre, u.rol, s.expira
                   FROM seguridad.sesiones s JOIN seguridad.usuarios u ON u.id = s.usuario_id
                   WHERE s.token_hash = %s AND NOT s.revocada AND s.expira > now() AND u.activo""",
                (h,),
            )
        except Exception:
            return None
        if not filas:
            self._cache.pop(h, None)
            return None
        id_, u, nombre, rol, expira = filas[0]
        sesion = SesionActiva(id_, u, nombre, rol, expira)
        self._cache[h] = (sesion, ahora + CACHE_SESION_S)
        return sesion

    async def logout(self, token: str, usuario: str, ip: str | None) -> None:
        h = _sha(token)
        self._cache.pop(h, None)
        await self._ejecutar(
            "UPDATE seguridad.sesiones SET revocada = true WHERE token_hash = %s", (h,)
        )
        await self.registrar(usuario, "logout", ip, None)

    async def _revocar_sesiones(self, usuario_id: int) -> None:
        await self._ejecutar(
            "UPDATE seguridad.sesiones SET revocada = true WHERE usuario_id = %s AND NOT revocada",
            (usuario_id,),
        )
        for clave, (sesion, _) in list(self._cache.items()):
            if sesion.usuario_id == usuario_id:
                self._cache.pop(clave, None)

    # ------------------------------------------------------------------ historial
    async def registrar(self, usuario: str, evento: str, ip: str | None, detalle: str | None) -> None:
        try:
            await self._ejecutar(
                "INSERT INTO seguridad.accesos (usuario, evento, ip, detalle) VALUES (%s, %s, %s, %s)",
                (usuario[:60] or "?", evento, ip, (detalle or "")[:300] or None),
            )
        except Exception as exc:
            log.warning("No se pudo registrar el acceso: %s", _ascii_seguro(str(exc)))

    async def accesos(self, limite: int = 200) -> list[dict]:
        filas = await self._consultar(
            "SELECT id, ts, usuario, evento, ip, detalle FROM seguridad.accesos "
            "ORDER BY ts DESC LIMIT %s", (max(1, min(1000, limite)),)
        )
        return [
            {"id": f[0], "ts": f[1], "usuario": f[2], "evento": f[3],
             "ip": f[4], "detalle": f[5]}
            for f in filas
        ]

    # ------------------------------------------------------------------ usuarios
    async def usuarios(self) -> list[dict]:
        filas = await self._consultar(
            "SELECT id, usuario, nombre, rol, activo, creado, ultimo_acceso "
            "FROM seguridad.usuarios ORDER BY usuario"
        )
        return [
            {"id": f[0], "usuario": f[1], "nombre": f[2], "rol": f[3], "activo": f[4],
             "creado": f[5], "ultimo_acceso": f[6]}
            for f in filas
        ]

    async def crear(self, usuario: str | None, nombre: str | None, rol: str | None,
                    password: str | None, actor: str, ip: str | None) -> str | None:
        """Devuelve ``None`` si todo va bien, o el mensaje de error."""
        u = (usuario or "").strip().lower()
        if not USUARIO_VALIDO.match(u):
            return "Usuario: 3-40 caracteres (letras, números, punto, guion)"
        if not (nombre or "").strip():
            return "Falta el nombre"
        if rol not in ROLES:
            return "Rol inválido"
        error = validar_password(password)
        if error:
            return error
        try:
            await self._ejecutar(
                "INSERT INTO seguridad.usuarios (usuario, nombre, rol, hash) VALUES (%s, %s, %s, %s)",
                (u, nombre.strip(), rol, hashear(password or "")),
            )
        except psycopg.errors.UniqueViolation:
            return "Ese usuario ya existe"
        await self.registrar(actor, "usuario_creado", ip, f"{u} ({rol})")
        return None

    async def actualizar(self, id_: int, nombre: str | None, rol: str | None,
                         activo: bool | None, password: str | None,
                         actor: SesionActiva, ip: str | None) -> str | None:
        if rol is not None and rol not in ROLES:
            return "Rol inválido"
        if password is not None:
            error = validar_password(password)
            if error:
                return error
        if id_ == actor.usuario_id and (activo is False or (rol is not None and rol != "admin")):
            return "No puedes quitarte el rol de admin ni desactivarte a ti mismo"

        filas = await self._consultar(
            "SELECT usuario, rol, activo FROM seguridad.usuarios WHERE id = %s", (id_,)
        )
        if not filas:
            return "Usuario no encontrado"
        usuario, rol_actual, activo_actual = filas[0]

        quita_admin = rol_actual == "admin" and activo_actual and (
            (rol is not None and rol != "admin") or activo is False
        )
        if quita_admin:
            admins = await self._consultar(
                "SELECT count(*) FROM seguridad.usuarios WHERE rol = 'admin' AND activo"
            )
            if admins and int(admins[0][0]) <= 1:
                return "Debe quedar al menos un admin activo"

        await self._ejecutar(
            """UPDATE seguridad.usuarios SET
                 nombre = COALESCE(%s, nombre), rol = COALESCE(%s, rol),
                 activo = COALESCE(%s, activo), hash = COALESCE(%s, hash)
               WHERE id = %s""",
            (nombre.strip() if nombre else None, rol, activo,
             hashear(password) if password else None, id_),
        )
        # Cambio de rol, desactivación o nueva contraseña → se cierran sus sesiones.
        if rol is not None or activo is False or password is not None:
            await self._revocar_sesiones(id_)
        cambios = ", ".join(
            parte for parte in (
                "nombre" if nombre else None,
                f"rol={rol}" if rol else None,
                "activo" if activo is not None else None,
                "contraseña" if password else None,
            ) if parte
        )
        await self.registrar(actor.usuario, "usuario_modificado", ip, f"{usuario}: {cambios}")
        return None
