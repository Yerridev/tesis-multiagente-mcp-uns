# 06 · Despliegue con Docker — MCP-INDUSTRIAL-NET

## 1. Requisitos

- Docker Desktop (probado con Engine v29.1.3) y Docker Compose v2.
- `.env` copiado de `.env.example` (nunca subirlo).
- Servicio Windows de Mosquitto de la tesis corriendo (lo alimenta el espejo) — o
  eliminar `mirror-tesis` si no se usa la tesis.

## 2. Comandos

```powershell
cp .env.example .env                      # completar contraseñas/keys
docker compose config                      # validar (exit 0)
docker compose build                       # construir imágenes
docker compose --profile simulation up -d  # stack completo de pruebas
docker compose --profile monitoring up -d  # grafana + prometheus
docker compose ps
docker compose logs -f backend
docker compose images
docker compose top
docker compose down                        # parar (los volúmenes persisten)
docker compose down -v                     # BORRAR datos (solo si se quiere reiniciar limpio)
```

Perfiles: `core` · `simulation` · `monitoring` · `edge`.
`compose.override.yaml` (desarrollo/lab) se aplica solo: Mosquitto anónimo,
`mirror-tesis`, backend en `127.0.0.1:5295` y Grafana en `127.0.0.1:3000`.

## 3. Variables principales (.env)

| Variable | Default | Nota |
|---|---|---|
| FRONTEND_PORT | 8080 | único puerto publicado a la LAN |
| OPENROUTER_API_KEY | vacía | clave SOLO por entorno; rote la clave vieja |
| CONTROL_MODO | DryRun | no cambiar |
| CONECTOR_MODO | simulador (en .env de pruebas) | dry-run en edge |
| POSTGRES_* / INGESTOR_PASSWORD / BACKEND_RO_PASSWORD | ejemplos | cambiar en cualquier despliegue real |
| GRAFANA_ADMIN_PASSWORD | cambiar_esto | cambiar |

## 4. Resultado de las pruebas obligatorias (29-oct-2026)

| # | Prueba | Resultado |
|---|---|---|
| — | `docker compose config` | ✅ exit 0 |
| — | `docker compose build` | ✅ todas las imágenes |
| — | `docker compose --profile simulation up -d` | ✅ 8 contenedores + mirror |
| — | `docker compose ps` | ✅ todos `healthy` |
| — | `docker compose logs` | ✅ sin errores activos (transitorios documentados abajo) |
| — | `dotnet test` | ✅ 25/25 |
| 1 | Servicios saludables | ✅ healthchecks OK (frontend/backend/mosquitto/db/ingestor/connector/mcp/agents) |
| 2 | Frontend abre | ✅ `http://localhost:8080` HTTP 200 (SPA) |
| 3 | REST vía Nginx | ✅ `/api/equipment` → 4 equipos |
| 4 | SignalR/WS vía Nginx | ✅ `negotiate` 200 + `101 Switching Protocols` en `/hubs/plant` |
| 5 | Simulador publica telemetría/estado | ✅ `control/state` con `modo: SIMULADOR` |
| 6 | Backend recibe datos | ✅ nivel: `plc=CONECTADO`, mensajes>70, nivel_cm=−0.4 (vía espejo) |
| 7 | Ingestor guarda mediciones | ✅ 1500+ filas, 33 señales, unidades validadas |
| 8 | Grafana consulta datos | ✅ `SELECT count(*) FROM mediciones` → 1233 (vía /api/ds/query) |
| 9 | Servidor MCP responde | ✅ 6 tools listadas + `estado_real` ejecutado por SSE |
| 10 | Agentes solo con herramientas permitidas | ✅ `modoControl=AGENTES-SOLO-LECTURA`, POST de control → **405** |
| 11 | Orden simulada con correlación → Confirmado (escrito=false) | ✅ `corr-docker-2` → Confirmado/escrito=false/DRY-RUN |
| 12 | Sin conector → Timeout | ✅ `Timeout / SIN_CONFIRMACION` |
| 13 | Reinicio no pierde datos | ✅ restart de timescaledb: 537→562 (volúmen) |
| 14 | Sin secretos incrustados | ✅ `OPENROUTER_API_KEY=` en env; sin `sk-or-` en `docker history` |
| 15 | Ninguna prueba escribe en 192.168.114.9 | ✅ conector solo SIMULADOR/DRY-RUN; sin `CONTROL_REAL`; 0/13 verificadas |
| — | `docker compose images` / `top` / `inspect` | ✅ usuarios `appuser`, redes y puertos verificados |

Transitorios vistos en logs (ya resueltos): error de `05_seed.sql` por comentario mal
codificado (corregido y seed aplicado: 4 equipos); reinicio de DB durante la prueba 13
cortó una inserción del ingestor (se reconectó con backoff); `agents` reintentó MQTT al
arrancar antes que el broker (reconexión automática).

## 5. Cómo probar una orden

```powershell
$h=@{Authorization="Bearer dev-supervisor"}
Invoke-RestMethod "http://127.0.0.1:5295/api/control/nivel/comandos" -Method Post `
  -ContentType 'application/json' -Headers $h `
  -Body '{"tipo":"Setpoint","valor":10,"unidad":"cm","correlacion":"corr-1"}'
# Consultar estado:
Invoke-RestMethod "http://127.0.0.1:5295/api/control/nivel/comandos/<id>" -Headers $h
```
