# 05 · Arquitectura de contenedores — MCP-INDUSTRIAL-NET

*29-oct-2026 · control DRY-RUN · sin escritura al PLC.*

## 1. Diagrama resultante

```
Navegador
   │  http://<host>:8080
   ▼
[frontend] React + Nginx ──proxy /api, /hubs (WS)──► [backend] ASP.NET Core
                                                        ├── MQTT ──► [mosquitto] ◄─espejo─ [mirror-tesis] ◄─ broker Windows (tesis)
                                                        ├── SQL (lectura futura) ──► [timescaledb] ◄─ [ingestor-nivel]
                                                        ├── (lectura REST) ──► [mcp-nivel] (SSE, herramientas solo lectura)
                                                        └── agentes (misma imagen, AGENTS_ONLY=1) ──► [agents]
[connector-nivel] control MCN-09 (SIMULADOR/DRY-RUN) ──► [mosquitto]
[grafana] ──SQL──► [timescaledb]      [prometheus] ──métricas──► [grafana]
Red OT (desde el host): PLC 192.168.114.9:44818
```

## 2. Contenedores

| Contenedor | Imagen | Rol | Usuario |
|---|---|---|---|
| mcp-frontend | build `Dockerfile.frontend` (node→nginx) | SPA + proxy REST/SignalR con WebSocket | nginx (master root por la imagen oficial) |
| mcp-backend | build `Dockerfile.backend` (multi-stage .NET 10) | API, SignalR, roles, auditoría, control DRY-RUN, lectura MQTT | `appuser` (10001) |
| mcp-agents | build `Dockerfile.agents` (misma base, `AGENTS_ONLY=1`) | Agentes/consulta SOLO lectura: **sin** endpoints ni servicio de control | `appuser` |
| mcp-mosquitto | eclipse-mosquitto:2 | Broker del stack (dev: anónimo; prod: passwd+acl) | mosquitto |
| mcp-mirror-tesis | python:3.12-slim | Espejo **unidireccional** Windows→Docker del UNS de la tesis | root (imagen base) |
| mcp-timescaledb | timescale/timescaledb:2.17.2-pg16 | PostgreSQL+TimescaleDB con init de usuarios/esquema | postgres |
| mcp-ingestor-nivel | build `Dockerfile.ingestor` | MQTT→TimescaleDB idempotente con backoff y /healthz | `appuser` |
| mcp-connector-nivel | build `Dockerfile.connector` | conector de CONTROL (perfil simulation=simulador; edge=dry-run) | `appuser` |
| mcp-mcp-nivel | build `Dockerfile.mcp` | Servidor MCP SSE: 6 herramientas de lectura | `appuser` |
| mcp-grafana | grafana:11.3.0 | Dashboards aprovisionados (5) sobre TimescaleDB | grafana |
| mcp-prometheus | prom/prometheus:v2.55.1 | Ancla de monitoreo (scrapea Grafana; backend aún sin /metrics) | nobody |

## 3. Decisiones de diseño

### 3.1 Agentes: extracción mínima (sin reescritura)
El `AgentService`/`OpenRouterAgent` viven en el mismo proyecto y dependen de
`PlantState`/`NivelState` (telemetría). **Acoplamiento documentado**: separarlos en un
proyecto propio obligaría a duplicar MQTT, SignalR y modelos. Extracción mínima
realizada: **flag `AGENTS_ONLY=1`** que omite el registro de `ControlService`,
`ControlMqttService` y **todos** los endpoints `/api/control/*`. Verificado:
`POST /api/control/nivel/comandos` → **405** y `/health/ready` → `AGENTES-SOLO-LECTURA`.
Los agentes no pueden publicar órdenes ni cargar credenciales de control (el contenedor
ni siquiera recibe `Control__Usuarios`).

### 3.2 mcp-nivel
Servidor nuevo (`mcp/server_nivel.py`) con 6 herramientas **solo lectura**
(estado_actual, historial, diagnostico, metadatos, grafo_conocimiento, calidad_frescura)
que consumen el REST del backend; el knowledge graph viaja versionado
(`mcp/grafo_nivel.json`, copia del grafo de la tesis). **No hay herramientas de
escritura**: las órdenes pasan únicamente por el servicio de control determinista.
Transporte SSE en :8000 (interno). Nota: se fijó `mcp>=1.16,<2` porque en mcp 2.x
FastMCP se renombró a MCPServer.

### 3.3 Broker: espejo en vez de tocar la tesis
El servicio **Windows Mosquitto de la tesis** posee `127.0.0.1:1883` del host y solo
escucha en loopback: un puente desde el contenedor no podía alcanzarlo. Solución:
`mirror-tesis` (cliente MQTT en contenedor) suscribe `uss/…/sl01la07/#` del broker
Windows y re-publica en el broker del stack (**una sola dirección**, sin bucles, sin
tocar la configuración de la tesis).

### 3.4 Connector: acceso al PLC desde Docker
**Probado empíricamente:** un contenedor SÍ alcanza `192.168.114.9:44818`
(NAT de Docker Desktop). Se conserva igualmente el perfil **edge** y la recomendación
de correr el conector en la PC (docs/08) por estabilidad y para el modo real.

## 4. Imágenes y perfiles

- Perfiles: `core` (frontend, backend, mosquitto, timescaledb, mirror) ·
  `simulation` (+ ingestor-nivel, connector-nivel en simulador, mcp-nivel, agents) ·
  `monitoring` (grafana, prometheus) · `edge` (connector-nivel preparado, DRY-RUN).
- **No existe ningún perfil que active escritura real.**

## 5. Pendientes honestos

- `ordenes_control` y `eventos_auditoria` están creados y con grants, pero el backend
  aún no persiste en SQL (solo JSONL): los dashboards de órdenes mostrarán 0 hasta
  implementar el espejo a BD.
- Backend no consume aún TimescaleDB para lecturas (solo readiness); el histórico
  `.lvm` NO se migró (requiere prueba y respaldo).
- Prometheus solo scrapea Grafana: el backend no expone `/metrics` todavía.
