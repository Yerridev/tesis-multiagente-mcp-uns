# 09 · Migración del backend de C# a Python

**Fecha:** 2026-11-19 · **Alcance:** backend (REST + hub de telemetría + auth +
control remoto + agente + conversaciones + infra Docker).
**El frontend React, los conectores edge, los servidores MCP y los simuladores
NO se tocaron** (salvo el canal de telemetría, que pasó de SignalR a SSE).

---

## 1. Por qué

El proyecto tenía **un solo componente en C#** (backend ASP.NET Core 10,
20 446 líneas) sobre una base de datos y unos clientes ya en Python:

| Capa | Antes | Después |
|---|---|---|
| Campo (4 PLC) | — | igual |
| Edge (conectores) | Python | igual |
| Broker / BD | Mosquitto + TimescaleDB | igual |
| **Backend** | **ASP.NET Core 10** | **FastAPI (Python 3.12)** |
| MCP / agentes | Python (FastMCP SSE) | igual |
| HMI | React 19 + TS + Vite | igual (el canal pasa a SSE) |

Ventajas: una sola cadena de herramientas y **un solo lenguaje** para el
backend, los agentes y los conectores; el `mcp/` y el backend comparten ahora
el mismo cliente MQTT (`paho-mqtt`) y el mismo cargador de `.env`.

---

## 2. Decisiones de diseño

### 2.1 El canal de telemetría: SignalR → Server-Sent Events

El hub de SignalR del backend original era **solo de push**: el frontend
suscribía seis eventos (`telemetry`, `nivelSenales`, `caudalSenales`,
`presionSenales`, `temperaturaSenales`, `controlResultado`,
`temperaturaControlResultado`) y **nunca** invocaba un método del servidor.

| | SignalR (antes) | SSE (ahora) |
|---|---|---|
| Transporte | WebSocket / LongPolling | HTTP `text/event-stream` |
| Endpoint | `/hubs/plant` + `/negotiate` | `/api/stream` |
| Reconexión | `withAutomaticReconnect` | nativa de `EventSource` |
| Dependencia del front | `@microsoft/signalr` v9 | ninguna (API del navegador) |

Formato de un evento (RFC 8297):

```
event: telemetry
data: [{"id":"nivel-mcn09","value":12.5,…}]

```

El frontend cambió en **3 archivos**: `services/signalr.ts` → `services/stream.ts`,
`context/PlantContext.tsx` y los textos de las páginas. El evento `link`
(`connecting | connected | reconnecting | disconnected`) se conserva.

> `EventSource` no puede mandar cabeceras: el token de sesión viaja en el
> query `?access_token=` (el backend ya lo aceptaba para `/hubs`).

En Nginx hace falta una ubicación propia para `/api/stream` con
`proxy_buffering off` y `proxy_read_timeout 3600s` (si no, el proxy bufferiza
la respuesta y el navegador no ve nada hasta que termina).

### 2.2 El contrato HTTP se conserva **byte a byte**

El frontend da por hecho una forma muy concreta del JSON. Se reprodujeron
todos los detalles del serializador de .NET:

| Detalle | .NET | Python (FastAPI) |
|---|---|---|
| Nombre de las propiedades | camelCase | `alias_generator=to_camel` |
| Enums | texto (`"Confirmado"`) | `class X(str, Enum)` con el valor = nombre |
| Fechas | ISO-8601 con offset | `datetime` con zona horaria |
| Errores | `{"error":"CODIGO"}` | manejador global que **nunca** devuelve `{"detail":…}` |
| Cuerpo inválido | 400 | 400 `PETICION_INVALIDA` (no 422) |
| Rutas literales | antes que `{id}` | registro en ese orden |
| Código de orden | 202 con el **objeto orden** | igual (el front hace polling por `id`) |

Las 41 rutas del backend original están implementadas
(`backend/app/rutas/`): auth, equipment, history, latency, lienzo, control
(nivel + caudal + presión + temperatura), agent, mcp/catalogo, planta/sim.

### 2.3 Configuración

`appsettings.json` + variables de entorno con `__` como separador de sección
(`Mqtt__Host` → sección `Mqtt`, clave `Host`), igual que `IConfiguration`.
**Las variables de entorno tienen prioridad**, como en .NET.

> **Trampa de Windows:** `os.environ` normaliza las claves a MAYÚSCULAS, así que
> `Mqtt__Port` llega como `MQTT__PORT`. La resolución es **case-insensitive**
> (como la de .NET) para que las dos plataformas se comporten igual.

### 2.4 Base de datos

`psycopg` 3 (async) en lugar de `Npgsql`. El formato de hash **no cambia**:
PBKDF2-SHA256, 210 000 iteraciones, `pbkdf2-sha256$iter$salt_b64$hash_b64`.
`hashlib.pbkdf2_hmac` produce exactamente los mismos bytes, así que **las
contraseñas existentes siguen valiendo**.

La cadena de conexión de .NET (`Host=…;Port=…;Database=…`) se traduce al
formato libpq de `psycopg` automáticamente.

---

## 3. Pruebas

| Suite | Origen | Resultado |
|---|---|---|
| `backend/tests/test_control.py` | port de `ControlTests.cs` (xUnit → pytest) | 38 pruebas |
| `backend/tests/test_api.py` | contrato HTTP + SSE (nuevas) | 32 pruebas |
| `backend/tests/e2e.py` | extremo a extremo con un broker MQTT real | ✅ |

Las 38 pruebas del contrato de control cubren los 33 casos del backend .NET
más 5 nuevos. Todas las que verificaban el comportamiento **idéntico** se
mantienen tal cual; las que dependían de un detalle de implementación de .NET
se adaptaron al equivalente en Python (por ejemplo, el reloj controlable, que
en Python es un `callable` inyectado en el constructor).

```bash
cd backend
..\.venv\Scripts\python -m pytest -q          # 70 pruebas
..\.venv\Scripts\python tests\e2e.py --puerto 18830
```

---

## 4. Correcciones aplicadas (decisiones del proyecto)

| # | Hallazgo | Qué se hizo |
|---|---|---|
| **C-01** | `compose.yaml` armed `ControlCaudal/Presion/Temperatura` en **Real** + `HabilitadoEscritura=true` + `*_REAL=1` **hardcodeados**, contradiciendo la política de `.env.example` ("NO cambiar a Real") | Ahora vienen del `.env` con **valor por defecto seguro** (`DryRun` / `false` / `0`). Para escribir hay que armar los tres interruptores a propósito. |
| **C-02** | El comentario de `.env` decía que `CONTROL_PERMITIR_SENSOR_FUERA_DE_RANGO=1` habilitaba "órdenes" sin matizar, pero el setpoint **siempre** se rechazaba | Se mantiene el comportamiento **seguro** (el setpoint en cm se rechaza con el sensor saturado, porque pilotar contra un PV ficticio es peligroso) y se corrige la documentación. El override habilita las órdenes que **no** dependen del PV (arranque, parada, válvula) y las marca en la auditoría. |
| **C-03** | El backend de nivel aceptaba `AjustarValvula` (comando exclusivo del MCC-09) y lo publicaba al broker para que el conector lo rechazara | Se rechaza en el backend con `TIPO_DESCONOCIDO`, antes de publicar nada. |
| **C-04** | `ControlService.ProcesarAck` usaba `bool.Parse` sin guarda: un ack con `"escrito":"SIM"` lanzaba y se **descartaba el ack entero** | Parseo tolerante (`_bool_de`): nunca lanza. |
| **C-05** | `OrquestadorMultiagente` abría **una conexión MQTT nueva por petición** (el front consulta el catálogo cada 15 s) | Una sola conexión persistente con re-suscripción y caché del estado retenido. |
| **C-06** | `mcp/modulos.py` derivaba la base UNS del id de equipo, y en temperatura no coinciden (`temp-mct09` ≠ `temperatura-mct09`): la herramienta MCP `metadatos()` reportaba una base que **ningún publicador usa** | **Corregido en los dos repos**: `modulos.py` declara ahora `base_uns` por módulo y `server_modulo.py` la usa. El id del equipo (`temp-mct09`, el que ve el backend) y la base UNS (`temperatura-mct09`, la que usan los conectores) quedan explícitos y separados. |
| **C-07** | `README.md` describía "telemetría simulada" cuando el backend ya no simula nada | README reescrito con la arquitectura real. |
| **C-08** | Los `.bat`/`docs` seguían indicando `dotnet run` / `dotnet test` | Actualizados a `python run.py` / `pytest`. |

### Correcciones internas del port

| # | Hallazgo | Qué se hizo |
|---|---|---|
| **P-01** | `ControlService` y `ControlModulo` usaban `bool.Parse`/`Enum.TryParse` con semántica de .NET | Reimplementado con parseo tolerante. |
| **P-02** | `asyncio.Lock` no admite `with` (solo `async with`) | `PlantState` y `EstadoModulo` usan `threading.Lock` (se acceden desde el bucle y desde el hilo de MQTT). |
| **P-03** | `datetime` naive serializado sin offset → `new Date()` lo interpretaría como hora local | Todos los `datetime` son *aware*; el SSE usa un serializador ISO. |
| **P-04** | Doble definición de los enums `TipoComando`/`EstadoComando` (en `modelos.py` y en `control/contrato.py`) → las comparaciones `is` fallaban en silencio | Una sola fuente de verdad: `app/modelos.py`. |
| **P-05** | `JSONResponse` no serializa `datetime` | `OrdenControl.para_senal()` emite ISO-8601 (igual que .NET). |
| **P-06** | `PowerShell 5.1 -Encoding UTF8` añade BOM → rompía el `package.json` de Vite | BOM eliminado de todo el repositorio (43 ficheros). |
| **P-07** | **`psycopg` en modo async no funciona con el `ProactorEventLoop`** (el que usa asyncio por defecto en **Windows**): el backend no arrancaba contra TimescaleDB en la PC del laboratorio | Se fija `asyncio.WindowsSelectorEventLoopPolicy()` al importar `app.main` (y en `run.py`), que es lo que indica el propio error de psycopg. En Linux/Docker no aplica. |
| **P-08** | Los mensajes de error de PostgreSQL vienen en UTF-8 y la consola de Windows usa cp1252: un `log.warning` con un carácter no representable **rompía la tarea** que estaba escribiendo | `_ascii_seguro()` sanea el texto antes de loguearlo. |

### Rotación de secretos (2026-11-19)

Se auditó la exposición real antes de rotar:

* `.env` **nunca** se commiteó (`.gitignore` lo cubre y `git log --all -- .env`
  no devuelve nada).
* Se barrieron **todos los blobs** del historial de las tres ramas remotas:
  **no hay ninguna clave de OpenRouter completa** en git. Lo único que aparece
  es el prefijo truncado `sk-or-v1-6d65…` dentro de una nota de
  `docs/07-redes-y-seguridad-docker.md`.
* La exposición real eran **los dos `.env` en disco** (el original y la copia
  `-py`).

Se rotaron: `OPENROUTER_API_KEY`, `ADMIN_PASSWORD`, `SERVICIO_TOKEN`,
`POSTGRES_PASSWORD`, `INGESTOR_PASSWORD`, `BACKEND_RO_PASSWORD` y
`GRAFANA_ADMIN_PASSWORD`.

Dos detalles que no son evidentes:

1. **Cambiar la variable no cambia la contraseña.** `GF_SECURITY_ADMIN_PASSWORD`
   (Grafana) y `POSTGRES_PASSWORD` (Postgres) solo se aplican al **crear** el
   usuario la primera vez. Hubo que cambiarlas **dentro** de los servidores:
   `ALTER ROLE …` en Postgres y
   `grafana cli --homepath /usr/share/grafana admin reset-admin-password` en
   Grafana. Después se recrearon los contenedores afectados para que lean el
   `.env` nuevo.
2. **El hash del admin** se regeneró con el PBKDF2 del backend Python
   (`app/seguridad/store.py`), que es **byte-compatible** con el de .NET: el
   backend C# aceptó el login con la clave nueva nada más escribirla. Eso
   demuestra la compatibilidad entre los dos backends con las mismas cuentas.

Verificado: login nuevo → 200 · login viejo → 401 · token de servicio nuevo →
200 · token viejo → 401 · los 3 ingestores siguen conectados con la clave
nueva de la base.

---

## 5. Lo que **no** se tocó

* Los **conectores edge** y de control (`conectores/`): son la única capa que
  escribe en el PLC y ya estaban en Python.
* Los **servidores MCP**, el orquestador y los analistas (`mcp/`).
* Los **simuladores** (`simulador/`).
* El **ingestor** de TimescaleDB (`ingestor/`).
* El **frontend**, salvo el canal de telemetría y los textos que lo nombraban.

---

## 6. Pendientes conocidos

1. ~~**`mcp/modulos.py`** (`uns_base` de temperatura)~~ → **RESUELTO** (ver C-06).
2. **`PotenciaVariador`** está declarado en el contrato del backend pero el
   conector de nivel no tiene mapeo a ninguna dirección (`N7:0` no está en la
   allowlist). Hoy el conector responde `SIN_DIRECCION_CANDIDATA`. Si el
   laboratorio lo necesita, hay que añadir `N7:0` a la allowlist **y** al
   conector, y verificarlo en el ladder.
3. **Clave de OpenRouter**: la anterior se retiró de los `.env` (estaba en
   claro). Hay que **generar una nueva** en <https://openrouter.ai/keys>,
   pegarla en `OPENROUTER_API_KEY` en los dos repos y **revocar la anterior**
   en el panel de OpenRouter. Sin ella el agente funciona con las reglas
   deterministas (degradado, pero funcional).
4. La rejections del MCN-09 devuelven **la orden** (con `motivo`), igual que
   el backend .NET; el frontend muestra `HTTP 409` en vez del motivo. Se puede
   mejorar añadiendo `error` al cuerpo de la orden (campo aditivo, no rompe el
   contrato).

---

## 7. Cómo arrancar

```bash
# backend
cd backend; ..\.venv\Scripts\python run.py --puerto 5051

# frontend (desarrollo)
cd frontend; npm run dev      # http://localhost:5173
```

Docker: `docker compose --profile core up -d --build`
(perfiles: `core | simulation | monitoring | edge`).

La API documentada está en `/api/docs` (OpenAPI generado por FastAPI).
