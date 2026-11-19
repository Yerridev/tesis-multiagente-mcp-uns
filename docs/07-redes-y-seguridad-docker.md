# 07 · Redes y seguridad en Docker — MCP-INDUSTRIAL-NET

## 1. Redes (mínimo privilegio)

| Red | Miembros | ¿Publica a la LAN? |
|---|---|---|
| `frontend_net` | frontend, backend | solo `frontend` publica **8080** |
| `application_net` | backend, mosquitto, ingestor-nivel, mcp-nivel, agents, mirror-tesis | no |
| `data_net` (internal) | backend, timescaledb, ingestor-nivel, grafana | no — red aislada, 5432 sin publicar |
| `monitoring_net` | grafana, prometheus | no |
| `control_net` | mosquitto, connector-nivel | no |

Verificado con `docker inspect`:
`backend → frontend+application+data` · `connector → control` · `db → data (5432/tcp: null)`.

## 2. Puertos

| Puerto | Servicio | Exposición |
|---|---|---|
| 8080 | frontend (Nginx) | **0.0.0.0** (único público, perfil dev/lab) |
| 5295 | backend | **127.0.0.1** (solo loopback) |
| 3000 | Grafana | **127.0.0.1** |
| 1883 | Mosquitto | NO publicado en este stack (ver §4) |
| 5432 | TimescaleDB | NO publicado (internal) |
| 8000/8098/8099 | mcp/connector/ingestor health | solo dentro de la red |

## 3. Usuarios y credenciales

- Contenedores de aplicación: `appuser` uid 10001 (no root). Frontend usa el usuario
  `nginx` de la imagen oficial (el master nginx arranca como root: característica de la
  imagen; los workers corren como nginx — anotado como riesgo bajo aceptado).
- Postgres: superuser solo para mantenimiento; `ingestor` escribe SOLO
  `equipos/senales/mediciones`; `backend_ro` y `mcp_reader` solo lectura (init SQL en
  `deploy/postgres/init/`).
- Mosquitto (producción): `allow_anonymous false` + `passwd` + `acl`
  (`deploy/mosquitto/mosquitto.conf`, `acl.example`) con usuarios `backend_reader`,
  `ingestor`, `connector_level`, `control_level` — el de control solo:
  `read funcional/#` + `read control/cmd` + `write control/ack|state` (sin `#` global).
  En desarrollo (`mosquitto-dev.conf`) se permite anónimo SOLO para el lab local.

## 4. Secretos

- `backend/appsettings.json` ya **no contiene** la clave de OpenRouter (vacía);
  se inyecta con `OPENROUTER_API_KEY` desde `.env` (gitignored).
- `docker inspect mcp-backend` confirma `OPENROUTER_API_KEY=` vacío y
  `docker history` no contiene `sk-or-`.
- ✅ **Rotación de secretos (2026-11-19)**: se comprobó que **ninguna clave
  completa está en el historial de git** (`git log --all -S "sk-or-v1-"` solo
  encuentra el prefijo truncado `sk-or-v1-6d65…` de esta misma nota; el barrido
  de todos los blobs no encuentra ninguna clave de 20+ caracteres). La exposición
  real eran los archivos `.env` en disco. Se rotaron:
  `OPENROUTER_API_KEY` (retirada, hay que generar otra y revocar la anterior
  en openrouter.ai), `ADMIN_PASSWORD`, `SERVICIO_TOKEN`, `POSTGRES_PASSWORD`,
  `INGESTOR_PASSWORD`, `BACKEND_RO_PASSWORD` y `GRAFANA_ADMIN_PASSWORD`.
  Las contraseñas de la base y de Grafana se cambiaron **dentro** de los
  servidores (`ALTER ROLE` y `grafana cli admin reset-admin-password`), no solo
  en el `.env`: `GF_SECURITY_ADMIN_PASSWORD` y las variables de Postgres solo
  se aplican al crear el usuario la primera vez.
  Comprobado: la clave nueva entra y la anterior devuelve 401.
- `deploy/secrets/` ignorado por git salvo su README (cómo generar passwd/MQTT).

## 5. Reglas de seguridad cumplidas

- Sin `privileged: true` · sin `/var/run/docker.sock` · sin capabilities extra.
- Servicios de datos no publicados; solo frontend (y backend/Grafana en loopback).
- El PLC no participa en healthchecks; `ready` lo reporta como dependencia degradada.
- Control: `Control__HabilitadoEscritura=false`, sin `CONTROL_REAL`, 0/13 direcciones
  verificadas; `agents` sin endpoints de control (405) y sin secretos de control.
- El LLM (OpenRouter) conserva solo herramientas de lectura.
