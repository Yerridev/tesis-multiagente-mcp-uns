# Arquitectura multiagente de IA para la integración de datos industriales mediante MCP

Tesis de Ingeniería de Sistemas — **Universidad Señor de Sipán (USS)**, Chiclayo, Perú.
Entorno experimental: **Laboratorio de Automatización y Simulación de Procesos** (aula SL01LA07), 4 módulos didácticos:

| Equipo | Módulo | Controlador | Protocolo | IP |
|---|---|---|---|---|
| `caudal-mcc09` | MCC-09/002 | Siemens S7-200 CPU 226 + CP243-1 | S7 (snap7) | 192.168.114.7 |
| `presion-mcp09` | MCP-09/001 | NI Compact FieldPoint cFP-2200 | NI-PSP / DataSocket | 192.168.114.8 |
| `nivel-mcn09` | MCN-09/001 | Allen-Bradley MicroLogix 1100 | EtherNet/IP (pycomm3) | 192.168.114.9 |
| `temperatura-mct09` | MCT-09/001 | Schneider Twido | Modbus TCP | 192.168.114.10 |

> **Principio rector:** los agentes de IA (LLM) **solo leen**. Todas las herramientas MCP son de lectura y el servicio MCP entra al backend con rol `viewer`. El control de la planta (stack v2) es una función **de operador humano**, apagada por defecto (`CONTROL_MODO=DryRun`). Ver [Decisiones pendientes](#decisiones-pendientes).

---

## Dos stacks en un mismo repositorio

El repo junta dos etapas del proyecto. **Ninguna reemplaza a la otra todavía**: cada una tiene una función en la tesis.

| | **Stack v2 — MCP Industrial Net** (oficial) | **Stack v1 — Historiador** (experimento) |
|---|---|---|
| Carpetas | raíz: `backend/` `frontend/` `mcp/` `conectores/` `ingestor/` `simulador/` `deploy/` `bat/` `docs/` `tests/` | `historiador/` `nivel/` `presion/` `temperatura/` |
| Para qué | Plataforma final: SCADA web de los 4 módulos, lienzos, login y roles, sistema multiagente, simulador de los 4 PLC, monitoreo | Investigación de campo de los PLC, histórico `.lvm` (2008–2012), **experimento A/B/C/D (41 preguntas)** y **evaluación de 23 casos** |
| Tecnología | ASP.NET Core 10 + SignalR · React + TS + Vite · Nginx · FastMCP (Python) · Docker Compose | Python · FastAPI · React · FastMCP por stdio · Docker Compose |
| MQTT | Mosquitto en Docker (`1884` hacia la LAN) + `mirror-tesis` que espeja el broker de Windows (`1883`) | Mosquitto servicio de Windows (`1883`) |
| Base de datos | TimescaleDB `mcp-timescaledb` (red interna, sin puerto publicado) | TimescaleDB `uns-timescaledb` (`5432`) |
| Herramientas MCP | `estado_actual` · `senales` · `historial` · `diagnostico` · `metadatos` · `grafo_conocimiento` · `calidad_frescura` | `listar_variables` · `obtener_lectura` · `consultar_historial` · `obtener_estado_plc` · `comparar_con_rango` · `diagnosticar_*` · `consultar_grafo` |
| Interfaz | `http://localhost:8080` | Grafana `http://localhost:3000` · Lienzo `http://localhost:8765` |

Los dos pueden correr a la vez: no comparten contenedores ni puertos, salvo **Grafana (3000)**, que en v2 solo existe con el perfil `monitoring`.

**¿Por qué el experimento sigue en v1?** Sus respuestas correctas ("verdad de campo") salen de los datos guardados en `uns-timescaledb` y de las herramientas MCP de v1. Pasarlo a v2 cambiaría las herramientas y el esquema de datos, es decir, sería **otro experimento**. Para v2 ya existe su propio evaluador ([`tests/evaluacion/evaluar.py`](tests/evaluacion/evaluar.py), `bat/33`).

---

## Puesta en marcha en local

Requisitos: Windows 10/11, **Docker Desktop**, **Python 3.12**, Git. Para la planta real además: el cable del laboratorio y, para presión, las DLL de NI en `%NIDS_DIR%` (por defecto `%USERPROFILE%\NI-DS`).

### Stack v2 con la planta simulada (sin laboratorio)

```powershell
copy .env.example .env               # completar: ADMIN_PASSWORD, SERVICIO_TOKEN, OPENROUTER_API_KEY (opcional)
bat\00-instalar-python.bat           # una vez: crea .venv en la raíz
bat\10-simular-planta.bat            # 4 PLC virtuales + conectores + Docker en modo SIMULADO
```

Abrir `http://localhost:8080` y entrar con el usuario de `ADMIN_USUARIO` / `ADMIN_PASSWORD`.
Sistema multiagente: `bat\31-sistema-multiagente.bat` (dejar abierto), luego `bat\32-preguntar-agentes.bat`.
Para volver a la planta real: `bat\11-detener-simulacion.bat`.

### Stack v2 con la planta real (laboratorio)

```powershell
bat\01-red-laboratorio.bat           # IPs fijas en la tarjeta Ethernet + ping a los 4 PLC (pide administrador)
bat\02-iniciar-lectores-reales.bat   # lectores de caudal, presión y temperatura
```

> ⚠️ La **planta real y la simulada nunca a la vez**. La guía completa de los `.bat` está en [`bat/LEEME-BATS.md`](bat/LEEME-BATS.md).

### Stack v1 y experimento

```powershell
cd historiador
INICIAR_TODO.bat                                           # TimescaleDB + ingestores + Grafana + lienzo
EXPERIMENTO.bat --solo-verdad                              # revisa la verdad de campo, sin LLM
EXPERIMENTO.bat --modelos openrouter --configs A,B,C,D     # experimento
EVALUAR_CASOS.bat                                          # 23 casos verificados
```

Los servidores MCP de v1 (`historiador/mcp_servidor/servidor_mcp*.py`) son los que usa Claude Desktop (`caudal-mcc09`, `nivel-mcn09`, `presion-mcp09`, `temperatura-mct09`).

---

## Estructura

```text
├── backend/              ASP.NET Core 10: REST + SignalR, login y roles, control con auditoría, agente
├── frontend/             React + TS: SCADA de los 4 módulos, lienzos, agentes, usuarios
├── mcp/                  server_modulo.py (MCP por módulo), agentes/ (orquestador + analistas), conocimiento/
├── conectores/           edge (lectura) y control por PLC + lanzadores .ps1
├── ingestor/             ingestor MQTT → TimescaleDB (v2)
├── simulador/            4 PLC virtuales (S7, EtherNet/IP, Modbus, PSP) + modelos de planta
├── deploy/               mosquitto, postgres (init), grafana, prometheus, nginx, secrets
├── bat/                  scripts de operación (ver LEEME-BATS.md)
├── tests/                pruebas .NET (control), agentes, evaluación v2, capturas de la HMI
├── compose*.yaml         stack v2 (perfiles core · simulation · monitoring · edge)
├── docs/                 documentación (índice abajo)
│   └── tesis/            documentación del stack v1 y de la investigación de campo
├── historiador/          stack v1: conectores, ingestores, BD, Grafana, MCP, lienzo, orquestación, evaluación
├── nivel/  presion/  temperatura/   investigación de campo de cada PLC (mapas, pruebas, diagnóstico)
└── subir_github.ps1      script de subida del stack v1
```

---

## Documentación

**Plataforma (v2)**

| Documento | Contenido |
|---|---|
| [docs/05-arquitectura-contenedores.md](docs/05-arquitectura-contenedores.md) | Contenedores, redes y flujo de datos |
| [docs/06-despliegue-docker.md](docs/06-despliegue-docker.md) | Comandos, variables del `.env` y pruebas de despliegue |
| [docs/07-redes-y-seguridad-docker.md](docs/07-redes-y-seguridad-docker.md) | Segmentación de redes y puertos |
| [docs/08-operacion-edge-plc.md](docs/08-operacion-edge-plc.md) | Operación de los conectores edge |
| [docs/01-auditoria-control-remoto.md](docs/01-auditoria-control-remoto.md) | Auditoría del control remoto |
| [docs/02-mapa-verificacion-rslogix.md](docs/02-mapa-verificacion-rslogix.md) | Verificación de direcciones del MicroLogix |
| [docs/03-seguridad-control-remoto.md](docs/03-seguridad-control-remoto.md) | Enclavamientos, roles y riesgos del control |
| [docs/04-checklist-validacion-presencial.md](docs/04-checklist-validacion-presencial.md) | Checklist en el laboratorio |
| [docs/control-puesta-en-marcha.md](docs/control-puesta-en-marcha.md) | Puesta en marcha del control |
| [bat/LEEME-BATS.md](bat/LEEME-BATS.md) · [conectores/README_conectores.md](conectores/README_conectores.md) · [simulador/README.md](simulador/README.md) · [deploy/secrets/README.md](deploy/secrets/README.md) | Operación diaria, conectores, simulador y secretos |

**Tesis e investigación de campo (v1)**

| Documento | Contenido |
|---|---|
| [docs/tesis/00-tesis-v1-historiador.md](docs/tesis/00-tesis-v1-historiador.md) | README completo del stack v1: equipos, UNS, red, MCP, historiador, evaluación, glosario |
| [docs/tesis/01-estado-actual-v1.md](docs/tesis/01-estado-actual-v1.md) | Bitácora de avance por capa (al 23-oct) |
| [docs/tesis/02-red-laboratorio-plc.md](docs/tesis/02-red-laboratorio-plc.md) | Red, IPs, enlaces y TSAP de los PLC |
| [historiador/README.md](historiador/README.md) · [historiador/orquestacion/README.md](historiador/orquestacion/README.md) | Historiador y experimento A/B/C/D |
| [nivel/README.md](nivel/README.md) · [presion/README.md](presion/README.md) · [presion/RECUPERACION_cFP2200.md](presion/RECUPERACION_cFP2200.md) · [temperatura/README.md](temperatura/README.md) | Investigación de cada módulo |
| `docs/tesis/ANALISIS_CPU226.awl` · `docs/tesis/diagramas.xps` | Programa del S7-200 y diagramas |

---

## Seguridad

- Secretos solo en `.env` (no se sube). Copiar desde `.env.example` y cambiar **todas** las contraseñas de ejemplo.
- `CONTROL_MODO=DryRun` y `CONTROL_HABILITADOESCRITURA=false` por defecto. `compose.control-real.yaml` y `compose.temperatura-real.yaml` **activan la escritura real**: úsenlos solo en el laboratorio, con el responsable presente.
- Las claves `dev-*` de `backend/appsettings.json` solo valen si se apaga el login (`Auth:Habilitado=false`). Con el login activo, `/api` exige una sesión válida.
- El LLM no tiene ninguna herramienta de escritura.

## Decisiones pendientes

1. **Alcance del control:** la propuesta de tesis dice "integración de solo lectura". El stack v2 agrega control por operador humano. Hay que decidir si se declara en el informe (control supervisado, LLM solo lectura) o si se dejan fuera los perfiles `real`.
2. **Experimento en v2:** si se quiere medir la arquitectura final, hay que repetir el experimento con las herramientas de v2 (`tests/evaluacion/evaluar.py`) y reportarlo aparte del de v1.
3. **Un solo repositorio:** desde ahora se trabaja en este repo con ramas y PR (`git pull` / `git push`), en vez de copiar carpetas con los `.bat` 22–24.
