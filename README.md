# tesis-mcp-multiagent-uns

Bosquejo funcional del laboratorio de automatización (USS · UNS): supervisión,
SCADA web y **sistema multiagente MCP** sobre los cuatro módulos didácticos
INDUCONTROL (nivel MCN-09, caudal MCC-09, presión MCP-09, temperatura MCT-09).

**Stack actual: Python (FastAPI) + React/TypeScript + Vite.**
El backend es 100 % Python; ya no queda C# en el flujo.

```
┌─ Campo ────────────┐  ┌─ Edge (Python) ─┐  ┌─ Broker ──────────┐
│ 4 PLC reales       │→ │ conectores de   │→ │ Mosquitto +       │
│ MicroLogix/S7/cFP/ │  │ lectura/escritura│  │ TimescaleDB       │
│ Twido              │  └─────────────────┘  └────────┬──────────┘
└────────────────────┘                                │
                                          ┌────────────▼───────────┐
                                          │  backend (Python)      │
                                          │  FastAPI + SSE + auth  │
                                          │  control DRY-RUN       │
                                          └────────────┬───────────┘
┌─ Agentes (Python) ────────────┐                     │
│ 4 servidores MCP (SSE)         │←── MQTT ────────────┤
│ orquestador + 4 analistas      │                     │
│ OpenRouter                     │                     ▼
└────────────────────────────────┘            ┌────────────────┐
                                             │ SCADA web      │
                                             │ React 19 + Vite│
                                             └────────────────┘
```

## Puesta en marcha (local, sin Docker)

```bash
# 1) dependencias (Python 3.10+)
.venv\Scripts\python -m pip install -r backend\requirements.txt

# 2) compilar el frontend
cd frontend; npm install; npm run build; cd ..

# 3) copiar la SPA al backend y arrancar
copy frontend\dist\* backend\wwwroot\ /E
cd backend; ..\.venv\Scripts\python run.py --puerto 5051
```

Abrir <http://localhost:5051>.

La documentación de la API (OpenAPI) está en <http://localhost:5051/api/docs>.

### Pruebas

```bash
cd backend
..\.venv\Scripts\python -m pytest -q          # 70 pruebas (contrato + API)
..\.venv\Scripts\python tests\e2e.py --puerto 18830   # extremo a extremo con MQTT
```

## Despliegue (Docker)

> ⚠️ El `compose.yaml` de este repo está **renombrado a `mcp-industrial-py-NO-USAR`**
> a propósito: si se levantara, recrearía los contenedores `mcp-backend`,
> `mcp-frontend`, `mcp-mosquitto`… del stack del repo original y dejaría el
> laboratorio sin su stack C#.

Para probar el backend Python se usa el **stack paralelo** (proyecto `mcp-py`,
solo lectura):

```bat
bat\39-levantar-py-paralelo.bat     :: web en http://127.0.0.1:8181
bat\40-detener-py-paralelo.bat
```

Levanta **solo** `py-backend` y `py-frontend`, lee el Mosquitto del stack
original por la red `mcp-industrial_application_net` y **nunca** publica
órdenes: doble barrera (`Control__Publicar=false` en el backend + Nginx
bloqueando `POST/PUT` de `/api/control` y `/api/sim`).

El stack completo (`compose.yaml` con los perfiles `core | simulation |
monitoring | edge`) queda para cuando el backend Python sea el bueno: habrá
que quitarle el sufijo `NO-USAR` y renombrar los contenedores.

## Documentación

| Documento | Contenido |
|---|---|
| `docs/01-auditoria-control-remoto.md` | Auditoría del control remoto (guards, triple gate, confirmaciones) |
| `docs/02-mapa-verificacion-rslogix.md` | Mapa de verificación de direcciones en el ladder |
| `docs/03-seguridad-control-remoto.md` | Modelo de seguridad y roles |
| `docs/04-checklist-validacion-presencial.md` | Checklist de validación en el laboratorio |
| `docs/05-arquitectura-contenedores.md` | Arquitectura de contenedores |
| `docs/06-despliegue-docker.md` | Despliegue en Docker |
| `docs/07-redes-y-seguridad-docker.md` | Redes y seguridad del stack |
| `docs/08-operacion-edge-plc.md` | Operación del edge con los PLC |
| `docs/control-puesta-en-marcha.md` | Puesta en marcha del control remoto |
| `docs/09-migracion-backend-python.md` | **Migración del backend de C# a Python** |

## Estructura

```
backend/          backend Python (FastAPI) + pruebas
  app/            configuración, modelos, estado, mqtt, control, agentes, rutas
  tests/          pytest (contrato de control, API, extremo a extremo)
frontend/         SCADA web (React 19 + TypeScript + Vite)
mcp/              servidores MCP (SSE), orquestador y analistas multiagente
conectores/       conectores edge de los PLC (lectura y control)
simulador/        simuladores de planta y PLC virtuales
ingestor/         persistencia de señales en TimescaleDB
deploy/           nginx, mosquitto, postgres, grafana, prometheus
bat/              scripts de operación del laboratorio
docs/             documentación técnica
```
