# Arquitectura multiagente de IA para la integración de datos industriales mediante MCP

Tesis de Ingeniería de Sistemas — **Universidad Señor de Sipán (USS)**, Chiclayo, Perú.
Entorno experimental: **Laboratorio de Automatización y Simulación de Procesos** (aula SL01LA07).

> **Principio rector:** toda la integración es de **solo lectura**. Ningún componente escribe en los PLC, ni modifica su programa, la configuración de comunicaciones o las HMI. El LLM nunca tiene una vía hacia el control del proceso.

---

## Índice

1. [Resumen](#1-resumen)
2. [Estado actual](#2-estado-actual)
3. [Arquitectura](#3-arquitectura)
4. [Equipos integrados](#4-equipos-integrados)
5. [Red del laboratorio](#5-red-del-laboratorio)
6. [Unified Namespace (UNS)](#6-unified-namespace-uns)
7. [Estructura del repositorio](#7-estructura-del-repositorio)
8. [Puesta en marcha](#8-puesta-en-marcha)
9. [Servidor MCP y agentes](#9-servidor-mcp-y-agentes)
10. [Historiador y datos históricos](#10-historiador-y-datos-históricos)
11. [Evaluación experimental](#11-evaluación-experimental)
12. [Seguridad](#12-seguridad)
13. [Hoja de ruta](#13-hoja-de-ruta)
14. [Glosario](#14-glosario)

---

## 1. Resumen

El proyecto diseña e implementa una arquitectura en capas que:

1. **Adquiere** datos de PLC heterogéneos (Siemens y Allen-Bradley) con conectores edge de solo lectura.
2. **Normaliza y distribuye** las mediciones por **MQTT** bajo una jerarquía **Unified Namespace (UNS)**.
3. **Almacena** el histórico en **TimescaleDB**, junto con los históricos del SCADA original (2008–2012).
4. **Expone** los datos a agentes de IA mediante un **servidor MCP** con herramientas controladas (rol de base de datos de solo `SELECT`).
5. **Orquesta** agentes de IA que responden en lenguaje natural con datos trazables (valor, unidad, hora, fuente y vigencia).

## 2. Estado actual

*Actualizado: 19-oct-2026*

| Componente | Caudal (MCC-09) | Nivel (MCN-09) |
|---|---|---|
| Comunicación con el PLC | ✅ Ethernet (CP243-1, S7, enlace 1) | ✅ Ethernet (EtherNet/IP, pycomm3) |
| Mapa de variables | ✅ Validado (PC Access + tabla PID) | 🟡 Borrador v0.1 (lógica ladder + prueba en marcha) |
| Calibración | ✅ Caudalímetro (13 puntos, R²=0,9997) | ⏳ Pendiente (2 puntos) |
| Conector edge → MQTT | ✅ `conector_edge_s7200.py` v3.2 | ✅ `conector_edge_ml1100.py` v0.1 (falta prueba en sitio) |
| Ingestor → TimescaleDB | ✅ `ingestor` | ✅ `ingestor-nivel` (prefijo `nivel-mcn09/`) |
| Históricos `.lvm` importados | ✅ 2008–2011 | ⏳ Pendiente |
| Dashboard Grafana | ✅ | ⏳ Pendiente |
| Servidor MCP | ✅ 7 herramientas + grafo de conocimiento | ⏳ Pendiente |
| Lienzo visual con agente | ✅ (Gemini) | ⏳ Pendiente |

## 3. Arquitectura

```text
┌───────────────────────── FUENTES INDUSTRIALES (laboratorio USS) ─────────────────────────┐
│  S7-200 CPU226 + CP243-1 (caudal)            MicroLogix 1100 + 1762-IF2OF2 (nivel)        │
│  192.168.114.7  · S7 / TCP 102                192.168.114.9  · EtherNet/IP / TCP 44818    │
└──────────────┬───────────────────────────────────────────────┬────────────────────────────┘
               │ solo lectura (snap7)                          │ solo lectura (pycomm3)
               ▼                                               ▼
     conector_edge_s7200.py                          conector_edge_ml1100.py
               │                                               │
               └──────────────── MQTT (Mosquitto, Windows) ────┘
                     uss/campus/lab-automatizacion/sl01la07/<equipo>/{funcional,descriptivo}/...
                                        │
                     ┌──────────────────┴──────────────────┐
                     ▼                                     ▼
            ingestor (caudal)                     ingestor-nivel           ◄── importar_lvm.py
                     └──────────────► TimescaleDB ◄────────┘                   (históricos SCADA)
                                        │
             ┌──────────────────────────┼───────────────────────────┐
             ▼                          ▼                           ▼
       Grafana :3000         Servidor MCP (rol mcp_lector)    Lienzo visual :8765
                                        │                      (React + agente Gemini)
                                        ▼
                          Agentes de IA (Claude Desktop / Gemini)
```

Capas y responsabilidades:

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Adquisición | Python (`python-snap7`, `pycomm3`) | Leer el PLC, convertir unidades, marcar tiempo, publicar por excepción y heartbeat |
| Integración | MQTT (Mosquitto) + UNS | Desacoplar productores y consumidores; contexto en la ruta del tópico |
| Historial | TimescaleDB (hypertable + agregado de 1 min) | Persistir mediciones en vivo (`uns`) e históricas (`lvm`) |
| Acceso para IA | Servidor MCP | Herramientas acotadas, validadas y de solo lectura |
| Agentes | LLM (Claude / Gemini) | Interpretar preguntas, invocar herramientas y responder con trazabilidad |
| Interfaz | Grafana + lienzo React | Visualización, tendencias, diagnóstico y chat con el agente |

## 4. Equipos integrados

### 4.1 Módulo de control de caudal MCC-09/002 — Siemens S7-200

| Elemento | Detalle |
|---|---|
| PLC | SIMATIC S7-200 CPU 226 + módulo Ethernet **CP243-1** |
| Programa | STEP 7-Micro/WIN V4.0 (respaldo `BK_S7-200_CPU226_ORIGINAL_2026-10-13.mwp`, exportación `ANALISIS_CPU226.awl`) |
| Medición | Caudalímetro Kobold DRG 4–20 mA, 0–141 L/min (calibrado) |
| Acceso | Enlace 1 del CP243-1 (TSAP 11.00), cliente autorizado `192.168.114.10` |
| Limitación | El CP243-1 rechaza leer AIW/AQW (error 0x03); se leen sus copias en memoria (MW3, MW2, MW25, VW8) |
| Detalle | [`historiador/README.md`](historiador/README.md) |

### 4.2 Módulo de control de nivel MCN-09/001 — Allen-Bradley MicroLogix 1100

| Elemento | Detalle |
|---|---|
| PLC | MicroLogix 1100 (`1763-LEC`) + **1762-IF2OF2** |
| Programa | RSLogix 500 (`upload final.RSS`), analizado sin RSLogix con `nivel/extract_rss.py` |
| Medición | Sensor ultrasónico TS-30S (mide distancia: `N7:4` baja al llenar) |
| Actuadores | Variador Altivar 11 + bomba Pentax Ultra 7; válvula Belimo LRB24-3 |
| Acceso | EtherNet/IP (PCCC) puerto 44818, `pycomm3.SLCDriver` |
| Situación | HMI y SCADA originales no operativos; el equipo funciona en modo manual |
| Detalle | [`nivel/README.md`](nivel/README.md) |

## 5. Red del laboratorio

| Equipo | IP | Función |
|---|---|---|
| S7-200 + CP243-1 (caudal) | `192.168.114.7` | Control del módulo de caudal |
| MicroLogix 1100 (nivel) | `192.168.114.9` | Control del módulo de nivel |
| Laptop de tesis (Windows 11) | `192.168.114.10` (IP adicional) | Conectores, Mosquitto, Docker, MCP |
| PC del laboratorio (Windows XP) | `192.168.114.70` | SCADA LabVIEW original de caudal (enlace 0 del CP243-1) |
| PC/pantalla HMI | `192.168.114.72` | HMI existente |
| VM Windows 7 | `192.168.114.30` | STEP 7-Micro/WIN y PC Access por USB/PPI (diagnóstico) |

Detalle de enlaces y TSAP: [`red_laboratorio_plc.md`](red_laboratorio_plc.md).

## 6. Unified Namespace (UNS)

```text
uss/campus/lab-automatizacion/sl01la07/<equipo>/
├── funcional/                 ← datos en vivo (un tópico por variable, retain)
│   ├── <grupo>/<variable>
│   ├── edge/estado            ONLINE / OFFLINE (Last Will)
│   ├── edge/heartbeat         cada 10 s
│   └── plc/conexion           CONECTADO / SIN_CONEXION
└── descriptivo/
    ├── variables              catálogo JSON (tag, dirección, unidad, descripción, estado)
    └── equipo                 ficha técnica del equipo
```

Equipos: `caudal-mcc09`, `nivel-mcn09`.

Formato de cada medición:

```json
{
  "value": 12305,
  "unit": "cuentas",
  "timestamp": "2026-10-19T18:29:35-05:00",
  "source": "edge-ml1100/N7:4",
  "tag": "NIVEL_RAW"
}
```

Política de publicación: **por excepción** (al cambiar el valor) y, como mínimo, cada 60 s (`--max-silencio`).

## 7. Estructura del repositorio

```text
tesis/
├── README.md                     ← este documento
├── estado_actual_tesis.md        ← bitácora de avance
├── red_laboratorio_plc.md        ← red, IPs y enlaces de los PLC
├── ANALISIS_CPU226.awl           ← exportación del programa del S7-200
├── diagramas.xps                 ← diagramas de la arquitectura
├── historiador/
│   ├── conector_edge_s7200.py    ← conector caudal (S7-200 → MQTT) v3.2
│   ├── conector_edge_ml1100.py   ← conector nivel (MicroLogix → MQTT) v0.1
│   ├── docker-compose.yml        ← TimescaleDB, ingestor, ingestor-nivel, Grafana, lienzo
│   ├── .env.example              ← plantilla de credenciales (copiar a .env)
│   ├── db/                       ← esquema SQL, Timescale, roles y migraciones
│   ├── ingestor/                 ← MQTT → TimescaleDB (VAR_PREFIX por equipo)
│   ├── herramientas/importar_lvm.py   ← históricos del SCADA LabVIEW
│   ├── mcp_servidor/             ← servidor MCP + grafo de conocimiento
│   ├── lienzo/                   ← interfaz visual (React + backend con agente)
│   ├── grafana/                  ← datasource y dashboards provisionados
│   ├── evaluacion/               ← reproducción de casos de prueba
│   └── README.md                 ← guía detallada del historiador (caudal)
└── nivel/
    ├── README.md                 ← guía del módulo de nivel
    ├── tags_nivel.yaml           ← diccionario de variables (borrador v0.1)
    ├── probe_ml1100.py           ← primera prueba de comunicación
    ├── scan_ml1100.py            ← escáner del mapa de datos (+ modo watch)
    ├── extract_rss.py            ← extractor de proyectos RSLogix 500
    ├── rss_dump.txt              ← lógica extraída del programa
    └── mapa_ml1100_*.json        ← lecturas completas del PLC
```

No se versionan: `.env`, entornos virtuales, logs, transcripciones de sesiones ni los binarios originales de los programas de PLC (`*.mwp`, `*.RSS`). Ver [`.gitignore`](.gitignore).

## 8. Puesta en marcha

### Requisitos

- Windows 11 con una IP en `192.168.114.0/24` (para caudal, exactamente `192.168.114.10`).
- **Docker Desktop**.
- **Mosquitto** en Windows con `listener 1883 0.0.0.0` y `allow_anonymous true`.
- Python 3.12 con: `pip install python-snap7 pycomm3 paho-mqtt "psycopg[binary]" olefile`.

### Pasos

```powershell
# 1) Infraestructura
cd historiador
copy .env.example .env               # definir contraseñas
docker compose up -d --build         # TimescaleDB, ingestor, ingestor-nivel, Grafana, lienzo
docker compose logs -f ingestor-nivel

# 2) Conectores (cada uno en su terminal)
python conector_edge_s7200.py                        # caudal
python conector_edge_ml1100.py                       # nivel (sin calibrar)
python conector_edge_ml1100.py --raw-vacio A --raw-lleno B   # nivel calibrado

# 3) Interfaces
#    Grafana:  http://localhost:3000
#    Lienzo:   http://localhost:8765
```

## 9. Servidor MCP y agentes

`historiador/mcp_servidor/servidor_mcp.py` se conecta con el rol **`mcp_lector`** (solo `SELECT`) y abre cada sesión en modo read-only.

| Herramienta | Función |
|---|---|
| `listar_variables` | Variables del UNS con dirección PLC, unidad y disponibilidad de datos |
| `obtener_lectura` | Último valor con antigüedad y estado **VIGENTE / DESACTUALIZADO** |
| `obtener_estado_plc` | Conector, PLC, modo, bomba y alarmas |
| `consultar_historial` | Estadísticas y serie resumida (`uns` o `lvm`) |
| `comparar_con_rango` | Contraste con `rangos_validados` |
| `verificar_coherencia_caudal` | PV del PID vs caudalímetro (dos medidas independientes) |
| `comparar_con_historico_lvm` | Desempeño actual vs SCADA original |
| `consultar_grafo` | Grafo de conocimiento del equipo (`conocimiento/grafo_mcc09.json`) |

**Agentes:** Claude Desktop (vía `claude_desktop_config.ejemplo.json`) y un agente en el lienzo visual con **Gemini** (Google AI Studio). Estrategia: primero un agente de consulta fiable y después la coordinación multiagente (consulta, análisis y coordinador), para medir qué aporta realmente la orquestación.

Caso de uso de referencia:

> *"¿Cuál es el caudal actual, cómo varió en los últimos 5 minutos y está dentro del rango?"*

El agente no inventa mediciones ni define límites por su cuenta: si un dato está desactualizado o el rango es provisional, lo dice.

## 10. Historiador y datos históricos

| Tabla | Contenido |
|---|---|
| `mediciones` | Hypertable `time, variable, valor, unidad, fuente ('uns'/'lvm'), direccion` |
| `mediciones_1min` | Agregado continuo (promedio, mínimo, máximo, muestras) |
| `eventos` | ONLINE/OFFLINE, CONECTADO/SIN_CONEXION, heartbeat |
| `variables` | Catálogo publicado por cada conector |
| `rangos_validados` | Rangos aceptados (**pendientes de validar con el responsable del laboratorio**) |

Las variables de nivel se guardan con prefijo `nivel-mcn09/` (por ejemplo `nivel-mcn09/nivel/raw`). Las de caudal mantienen sus nombres originales (`caudal/pv_pid`, `pid/kc`…).

Históricos del SCADA original: archivos `.lvm` de LabVIEW (caudal 2008–2011, ya importados; nivel 2008–2012, pendiente), importados de forma idempotente con `herramientas/importar_lvm.py`.

## 11. Evaluación experimental

`historiador/evaluacion/reproducir_casos.py` (o `EVALUAR_CASOS.bat`) ejecuta casos de consulta reproducibles y registra los resultados en `logs/evaluacion_casos.{json,md}`.

Indicadores:

| Indicador | Definición |
|---|---|
| Integridad de datos | Mediciones recibidas / esperadas |
| Latencia de integración | Lectura en el PLC → disponible en la base |
| Disponibilidad | Tiempo operativo del conector y del PLC |
| Exactitud de consulta | Respuestas cuyo valor, unidad y hora coinciden con la fuente |
| Éxito de orquestación | Tareas multipaso completadas correctamente |
| Tiempo de respuesta | Pregunta → respuesta final del agente |
| Tasa de errores | Lecturas fallidas, errores de herramientas, consultas incompletas |

## 12. Seguridad

- Conectores **sin funciones de escritura** (S7: solo lecturas `db_read`/`read_area`; MicroLogix: solo `plc.read`).
- Rol de base de datos `mcp_lector` solo con `SELECT`, y sesiones read-only.
- Secretos en `.env` (fuera del repositorio); `.env.example` como plantilla.
- PLC y broker solo en la red local del laboratorio.
- No se modifica el programa de los PLC, la configuración del CP243-1 ni las HMI.
- Cualquier función de escritura futura requeriría análisis de riesgos y aprobación del responsable del laboratorio.

## 13. Hoja de ruta

- [x] Comunicación Ethernet de solo lectura con el S7-200 (caudal)
- [x] Mapa de variables y calibración del caudalímetro
- [x] MQTT + UNS, ingestor, TimescaleDB y Grafana
- [x] Importación de históricos `.lvm` de caudal
- [x] Servidor MCP (7 herramientas + grafo de conocimiento)
- [x] Lienzo visual con agente (Gemini)
- [x] Comunicación EtherNet/IP con el MicroLogix 1100 (nivel)
- [x] Extracción del programa RSLogix 500 y mapa de variables preliminar
- [x] Conector de nivel e ingestor dedicado
- [ ] Calibración del nivel y confirmación de variables en hipótesis
- [ ] Importar los históricos `.lvm` de nivel
- [ ] Herramientas MCP y dashboard para nivel
- [ ] Orquestación multiagente sobre los dos equipos
- [ ] Rangos operativos validados por el laboratorio
- [ ] Campaña de evaluación y cálculo de indicadores

## 14. Glosario

| Término | Significado |
|---|---|
| PLC | Controlador lógico programable |
| HMI | Interfaz de operador |
| SCADA | Supervisión, control y adquisición de datos |
| CP243-1 | Módulo Ethernet del S7-200 |
| TSAP | Identificador de punto de acceso en comunicaciones S7 |
| EtherNet/IP / PCCC | Protocolo industrial de Rockwell y su encapsulado de comandos para SLC/MicroLogix |
| MQTT | Protocolo de mensajería publicar/suscribir |
| UNS | Unified Namespace: jerarquía común de datos industriales |
| MCP | Model Context Protocol: estándar para conectar LLM con herramientas y contexto |
| `.lvm` | Formato de medición de LabVIEW usado por los SCADA originales |
| Edge | Componente que corre junto al equipo y traduce sus datos al UNS |
