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

1. **Adquiere** datos de controladores heterogéneos (Siemens, Allen-Bradley, National Instruments y Schneider Electric) con conectores edge de solo lectura.
2. **Normaliza y distribuye** las mediciones por **MQTT** bajo una jerarquía **Unified Namespace (UNS)**.
3. **Almacena** el histórico en **TimescaleDB**, junto con los históricos del SCADA original (2008–2012).
4. **Expone** los datos a agentes de IA mediante un **servidor MCP** con herramientas controladas (rol de base de datos de solo `SELECT`).
5. **Orquesta** agentes de IA que responden en lenguaje natural con datos trazables (valor, unidad, hora, fuente y vigencia).

## 2. Estado actual

*Actualizado: 23-oct-2026*

| Componente | Caudal (MCC-09) | Nivel (MCN-09) | Presión (MCP-09) | Temperatura (MCT-09) |
|---|---|---|---|---|
| Comunicación con el controlador | ✅ Ethernet (CP243-1, S7, enlace 1) | ✅ Ethernet (EtherNet/IP, pycomm3) | ✅ NI-PSP vía DataSocket en la VM Windows 7 (recuperado el 21-oct, parado desde 2018) | ✅ Modbus TCP (Twido, pymodbus) |
| Mapa de variables | ✅ Validado (PC Access + tabla PID) | 🟡 Borrador v0.1 (lógica ladder + prueba en marcha) | 🟡 Variables compartidas `DATOS_PAC`/`pid`; la mayoría confirmadas en prueba | 🟡 v0.1: programa Twido + diagrama del SCADA + prueba en marcha |
| Calibración | ✅ Caudalímetro (13 puntos, R²=0,9997) | ⏳ Pendiente (2 puntos) | 🟡 Escala validada contra la HMI (manómetro averiado) | 🟡 Escala del SCADA (cuentas×100/4095); falta termómetro |
| Conector edge → MQTT | ✅ `conector_edge_s7200.py` v3.2 | ✅ `conector_edge_ml1100.py` | ✅ `conector_edge_cfp2200.py` v0.3 (en la VM) | ✅ `conector_edge_twido.py` v0.1 |
| Ingestor → TimescaleDB | ✅ `ingestor` | ✅ `ingestor-nivel` (prefijo `nivel-mcn09/`) | ✅ `ingestor-presion` (prefijo `presion-mcp09/`) | ✅ `ingestor-temperatura` (prefijo `temperatura-mct09/`) |
| Históricos `.lvm` importados | ✅ 2008–2011 | ⏳ Pendiente | ⏳ Pendiente (2008–2009) | ✅ 2009–2011 (13 archivos) |
| Dashboard Grafana | ✅ | ✅ | ✅ `presion_mcp09.json` | ✅ `temperatura_mct09.json` |
| Servidor MCP | ✅ + grafo de conocimiento | ✅ `servidor_mcp_nivel.py` | ✅ `servidor_mcp_presion.py` v1.0 + grafo | ✅ `servidor_mcp_temperatura.py` v1.0 + grafo |
| Lienzo visual con agente | ✅ (Gemini) | ✅ | ✅ | ✅ |
| Observación | — | Funciona en manual (HMI/SCADA no operativos) | ⚠️ El Altivar 11 ignora la consigna del PID (lazo abierto) | HMI y SCADA recuperados el 23-oct; ⚠️ relé de estado sólido de la resistencia en revisión |

## 3. Arquitectura

```text
┌───────────────────────── FUENTES INDUSTRIALES (laboratorio USS) ─────────────────────────┐
│  S7-200 CPU226 + CP243-1 (caudal)   MicroLogix 1100 (nivel)        cFP-2200 (presión)      │
│  192.168.114.7 · S7 / TCP 102       192.168.114.9 · EtherNet/IP    192.168.114.8 · NI-PSP │
└──────────────┬───────────────────────────────┬──────────────────────────────┬─────────────┘
               │ snap7 (laptop)                │ pycomm3 (laptop)             │ DataSocket (VM Win7 .30)
               ▼                               ▼                              ▼
     conector_edge_s7200.py          conector_edge_ml1100.py       conector_edge_cfp2200.py
               │                               │                              │
               └──────────────── MQTT (Mosquitto, laptop .10:1883) ───────────┘
                     uss/campus/lab-automatizacion/sl01la07/<equipo>/{funcional,descriptivo}/...
                                        │
                     ┌──────────────────┴──────────────────┐
                     ▼                                     ▼
   ingestor (caudal) · ingestor-nivel · ingestor-presion                   ◄── importar_lvm.py
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
| Adquisición | Python (`python-snap7`, `pycomm3`, NI DataSocket vía `pywin32`) | Leer el PLC, convertir unidades, marcar tiempo, publicar por excepción y heartbeat |
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
| Acceso | Enlace 1 del CP243-1 (TSAP 11.00), cliente autorizado `192.168.114.10` (la laptop pasó a `.12` el 23-oct-2026; ver conflicto de IP en [`red_laboratorio_plc.md`](red_laboratorio_plc.md)) |
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

### 4.3 Módulo de control de presión MCP-09/001 — NI Compact FieldPoint cFP-2200

| Elemento | Detalle |
|---|---|
| Controlador | **cFP-2200** (VxWorks, LabVIEW Real-Time 8.6, FieldPoint 6.0.2) + cFP-DI-301, cFP-DO-403, cFP-AIO-610 |
| Programa | `startup.rtexe` del proyecto `MOD_PRESION.lvproj` (Corporación Córdova, 2008–2009); variables compartidas `DATOS_PAC` y `pid` |
| Medición | Transmisor Danfoss MBS 3000, 0–6 bar, 4–20 mA → `psi = (mA − 4)/16 × 87` (validado contra la HMI) |
| Actuadores | Variador Altivar 11 + bomba Pentax Ultra U5; válvula proporcional Danfoss EV260B (0–10 V) |
| Acceso | NI-PSP (propietario, sin librería abierta) → driver NI-FieldPoint + DataSocket en la **VM Windows 7** (`192.168.114.30`) → MQTT |
| Situación | Recuperado el 21-oct-2026 (DIP, bootline de VxWorks, reinstalación, programa y variables). HMI TPC-2106T y SCADA operativos; manómetro averiado; **el Altivar toma la velocidad de su perilla frontal e ignora al PID** |
| Detalle | [`presion/README.md`](presion/README.md) · recuperación [`presion/RECUPERACION_cFP2200.md`](presion/RECUPERACION_cFP2200.md) · pruebas [`presion/pruebas_20261021.md`](presion/pruebas_20261021.md) |

### 4.4 Módulo de control de temperatura MCT-09/001 — Schneider Twido

| Elemento | Detalle |
|---|---|
| Controlador | **Twido TWDLCAE40DRF** (Ethernet integrado) + 2× **TWDAMM3HT**; IP `192.168.114.10` fija en su configuración |
| Programa | TwidoSuite (`Twido1.xtwd`, Inducontrol, 2009). El programa real es más nuevo: el SCADA usa %M41/%M42, ausentes en el respaldo |
| Medición | 2 Pt100 Danfoss MBT 5252 con transmisor 4–20 mA → `°C = cuentas × 100/4095` (escala del SCADA original) |
| Actuadores | Resistencia calefactora por PWM (relé de estado sólido FOTEK SSR-25DA-H); bomba Pentax Ultra U5 + Altivar 11; enfriador con serpentín |
| Acceso | Modbus TCP 502 (`%MWi` = registro *i*, `%Mi` = bobina *i*) desde la laptop, solo lectura |
| Situación | 23-oct-2026: HMI y SCADA recuperados (Industrial Automation OPC Servers 5.1, objeto Modbus `temp`, PollRate `0:01`; despliegue de `LIB_PC`/`LIB_HMI`); Altivar pasado de mando local a 2 hilos (`tCC=2C`, `AIt=10U`). **Relé de estado sólido sin disipador: calentó sin orden del PLC; en revisión** |
| Detalle | [`temperatura/README.md`](temperatura/README.md) · mapa [`temperatura/tags_temperatura.yaml`](temperatura/tags_temperatura.yaml) |

## 5. Red del laboratorio

| Equipo | IP | Función |
|---|---|---|
| S7-200 + CP243-1 (caudal) | `192.168.114.7` | Control del módulo de caudal |
| cFP-2200 (presión) | `192.168.114.8` | Control del módulo de presión |
| MicroLogix 1100 (nivel) | `192.168.114.9` | Control del módulo de nivel |
| PLC Schneider Twido TWDLCAE40DRF (temperatura) | `192.168.114.10` | Control del módulo de temperatura MCT-09/001; Modbus TCP 502 |
| Laptop de tesis (Windows 11) | `192.168.114.12` (IP adicional) | Conectores caudal/nivel/temperatura, Mosquitto, Docker, MCP |
| VM Windows 7 (VirtualBox) | `192.168.114.30` | **Conector de presión** (DataSocket); STEP 7-Micro/WIN y PC Access por USB/PPI |
| PC del laboratorio (Windows XP, LabVIEW 8.6) | `192.168.114.70` (original) · `.80` (temporal) | Una sola PC: SCADA de caudal con `.70` (enlace 0 del CP243-1); se cambió a `.80` para el SCADA de presión y la recuperación del cFP. Vuelve a `.70` |
| PC/pantalla HMI (caudal) | `192.168.114.72` | HMI existente |
| HMI NI TPC-2106T (presión) | `192.168.114.82` | HMI del módulo de presión |
| PC del laboratorio (misma PC XP) para temperatura | `192.168.114.100` | SCADA `MOD_TEMP.exe` + Industrial Automation OPC Servers (objeto Modbus `temp`) |
| HMI NI TPC-2106T (temperatura) | `192.168.114.101` | HMI del módulo de temperatura (depende del SCADA de la PC .100) |

La laptop debe tener la red Ethernet en perfil **Privado** y reglas de entrada para ICMP y TCP 1883; si no, la VM no llega a Mosquitto (ver [`red_laboratorio_plc.md`](red_laboratorio_plc.md)).

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

Equipos: `caudal-mcc09`, `nivel-mcn09`, `presion-mcp09`, `temperatura-mct09`.

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
│   ├── conector_edge_ml1100.py   ← conector nivel (MicroLogix → MQTT)
│   ├── conector_edge_cfp2200.py  ← conector presión (cFP-2200 → MQTT) v0.3, corre en la VM
│   ├── CONECTOR_CFP2200.bat      ← lanzador con reinicio automático (VM)
│   ├── INICIAR_TODO.bat          ← arranque de toda la arquitectura (doble clic)
│   ├── iniciar_arquitectura.ps1  ← lógica del arranque v2 (tolerante a equipos apagados)
│   ├── docker-compose.yml        ← TimescaleDB, ingestores (caudal, nivel, presión), Grafana, lienzo
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
└── presion/
    ├── README.md                 ← guía del módulo de presión
    ├── RECUPERACION_cFP2200.md   ← procedimiento de recuperación del controlador
    ├── pruebas_20261021.md       ← bitácora de pruebas en vivo
    ├── prueba_*_20261021.csv     ← datos exportados de las pruebas
    ├── probe_ni_vm*.py           ← sondeos OPC/DataSocket en la VM
    ├── herramientas/             ← diag_cfp.py (FTP) y probe_cfp.py (puertos)
    └── puente_presion_VI.md      ← alternativa descartada (puente LabVIEW)
```

No se versionan: `.env`, entornos virtuales, logs, transcripciones de sesiones ni los binarios originales de los programas de PLC (`*.mwp`, `*.RSS`). Ver [`.gitignore`](.gitignore).

## 8. Puesta en marcha

### Requisitos

- Windows 11 con la IP `192.168.114.12` en la red del laboratorio. Para caudal el equipo debe tener `192.168.114.10` (único cliente del enlace 1 del CP243-1), IP que hoy ocupa el Twido de temperatura: ver [`red_laboratorio_plc.md`](red_laboratorio_plc.md).
- **Docker Desktop**.
- **Mosquitto** en Windows con `listener 1883 0.0.0.0` y `allow_anonymous true`.
- Python 3.12 con: `pip install python-snap7 pycomm3 paho-mqtt "psycopg[binary]" olefile`.

### Arranque automático (recomendado)

`historiador/INICIAR_TODO.bat` ejecuta `historiador/iniciar_arquitectura.ps1` v2, que funciona con **cualquier combinación** de equipos encendidos (1, 2 o los 3):

1. Hace ping a `.7`, `.8` y `.9`; los equipos apagados se marcan y **no detienen** el arranque.
2. Levanta Docker (si está disponible) y aplica las migraciones pendientes (marca v3.2, `06_presion_v01.sql` si falta el rango de presión).
3. Abre una ventana por conector de la laptop (caudal, nivel) con bucle de reinicio y log en `logs\conector_<id>.log`.
4. Para presión, enciende la VM con `VBoxManage` (nombre en `VM_PRESION` del `.env`) y espera el latido MQTT del conector de la VM.
5. Prueba cada servidor MCP (`--probar`, log en `logs\mcp_probar_<id>.log`), registra en Claude Desktop los que falten y abre lienzo y Grafana.
6. Muestra una tabla RESUMEN por equipo.

En la VM, el conector arranca solo con un acceso directo a `CONECTOR_CFP2200.bat` en `shell:startup` (ver [`presion/README.md`](presion/README.md) §6).

### Pasos manuales

```powershell
# 1) Infraestructura
cd historiador
copy .env.example .env               # definir contraseñas
docker compose up -d --build         # TimescaleDB, 4 ingestores, Grafana, lienzo
docker compose logs -f ingestor-nivel

# 2) Conectores (cada uno en su terminal)
python conector_edge_s7200.py                        # caudal
python conector_edge_ml1100.py                       # nivel (sin calibrar)
python conector_edge_ml1100.py --raw-vacio A --raw-lleno B   # nivel calibrado
# presión: en la VM Windows 7
python conector_edge_cfp2200.py --broker 192.168.114.12      # o CONECTOR_CFP2200.bat
python conector_edge_twido.py                        # temperatura (Twido 192.168.114.10)

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

### Lienzo de supervisión multi-equipo (http://localhost:8765)

Todo se configura desde un **registro único**: `historiador/mcp_servidor/conocimiento/equipos.json`.

| Vista | Contenido |
|---|---|
| **Navegación lateral** | Árbol UNS: campus › aula › equipos, con un semáforo por equipo (gris = normal, ámbar = atención, rojo = alarma o sin datos) |
| **Vista general** (`#/`) | Una tarjeta por equipo: variable principal, mini tendencia de 30 min, modo, bomba, PLC y diagnóstico. Incluye la lista "Requiere atención" y el **agente coordinador** |
| **Lienzo del equipo** (`#/equipo/<id>`) | La misma plantilla para todos: knowledge graph animado, diagnóstico con cadena causal, tendencia, UNS en vivo, línea de tiempo y agente |

El agente abre los servidores MCP de **todos** los equipos registrados. Cada herramienta lleva el prefijo de su equipo (`caudal__diagnosticar_lazo`, `nivel__diagnosticar_nivel`, `presion__diagnosticar_presion`), así que una misma pregunta puede consultar y comparar varios módulos.

### Servidor MCP de presión

`servidor_mcp_presion.py` v1.0: `listar_variables`, `obtener_lectura`, `obtener_estado_plc`, `consultar_historial`, `comparar_con_rango` (3–40 psi del fabricante), `diagnosticar_presion` (con `momento` para reproducir el pasado) y `consultar_grafo` (`grafo_mcp09.json`, 14 nodos). Diagnósticos: `SIN_DATOS`, `SELECTOR_EN_0`, `SISTEMA_DETENIDO`, `MANUAL_EN_MARCHA`, `REMOTO_SIN_SETPOINT`, `ACTUADOR_NO_RESPONDE`, `SUBIENDO_A_SETPOINT`, `EN_SETPOINT`, `SOBRE_SETPOINT`, `FUERA_DE_SETPOINT`. Con los datos del 21-oct detectó correctamente el lazo abierto del Altivar (`ACTUADOR_NO_RESPONDE`).

### Servidor MCP de temperatura

`servidor_mcp_temperatura.py` v1.0: las 6 herramientas comunes (`consultar_historial` admite `fuente='lvm'` para el SCADA 2009–2011), `comparar_con_rango` (15–50 °C del fabricante) y `diagnosticar_temperatura` (con `momento`). Diagnósticos: `SIN_DATOS`, **`CALENTAMIENTO_SIN_ORDEN`** (sube con el lazo detenido: falla del relé de estado sólido), `SOBRE_LIMITE`, `FALLA_NIVEL`, `SELECTOR_EN_0`, `SISTEMA_DETENIDO`, `LAZO_SIN_PARAMETROS` (el PLC pierde SP y PID al apagarse), `RESISTENCIA_SIN_EFECTO`, `CALENTANDO_A_SETPOINT`, `EN_SETPOINT`, `SOBRE_SETPOINT` y `FUERA_DE_SETPOINT`. Grafo `grafo_mct09.json` (16 nodos).

**Agregar un PLC nuevo:**
1. Conector edge → MQTT bajo `uss/campus/lab-automatizacion/sl01la07/<id>/...`.
2. Servicio de ingestor con `VAR_PREFIX=<id>/` en `docker-compose.yml`.
3. Servidor MCP `servidor_mcp_<proceso>.py` con `listar_variables`, `obtener_lectura`, `_estado_enlace` y su `diagnosticar_*`.
4. Grafo `conocimiento/grafo_<id>.json`.
5. Entrada en `equipos.json`.
6. Opcional: reglas de visualización por nodo en `lienzo/frontend/src/nodes/lecturas.ts`. Sin reglas, cada nodo muestra sus variables de forma genérica.

## 10. Historiador y datos históricos

| Tabla | Contenido |
|---|---|
| `mediciones` | Hypertable `time, variable, valor, unidad, fuente ('uns'/'lvm'), direccion` |
| `mediciones_1min` | Agregado continuo (promedio, mínimo, máximo, muestras) |
| `eventos` | ONLINE/OFFLINE, CONECTADO/SIN_CONEXION, heartbeat |
| `variables` | Catálogo publicado por cada conector |
| `rangos_validados` | Rangos aceptados (**pendientes de validar con el responsable del laboratorio**) |

Las variables de nivel se guardan con prefijo `nivel-mcn09/` (por ejemplo `nivel-mcn09/nivel/raw`) las de presión con `presion-mcp09/` (por ejemplo `presion-mcp09/presion/psi`; migración `db/06_presion_v01.sql`) y las de temperatura con `temperatura-mct09/` (migración `db/07_temperatura_v01.sql`). Las de caudal mantienen sus nombres originales (`caudal/pv_pid`, `pid/kc`…).

Históricos del SCADA original: archivos `.lvm` de LabVIEW (caudal 2008–2011 y temperatura 2009–2011, ya importados; nivel 2008–2012 y presión 2008–2009, pendientes), importados de forma idempotente con `herramientas/importar_lvm.py`.

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

- Conectores **sin funciones de escritura** (S7: solo lecturas `db_read`/`read_area`; MicroLogix: solo `plc.read`; cFP-2200: DataSocket solo en modo `ReadAutoUpdate`).
- El Altivar 11 de presión no se reconfigura sin el responsable del laboratorio.
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
- [x] Herramientas MCP y dashboard para nivel
- [x] Recuperación del cFP-2200 de presión (parado desde 2018)
- [x] Lectura del cFP-2200 sin la PC del laboratorio (DataSocket en la VM), ingestor, MCP, Grafana y lienzo de presión
- [x] `INICIAR_TODO` tolerante a equipos apagados
- [ ] Calibración del nivel y confirmación de variables en hipótesis
- [ ] Importar los históricos `.lvm` de nivel y presión
- [ ] Altivar 11 de presión con consigna AI1 (con el responsable) y nueva prueba del lazo
- [ ] Casos de evaluación de presión
- [x] Módulo de temperatura: HMI y SCADA recuperados, conector Modbus, ingestor, MCP, Grafana, lienzo e históricos `.lvm`
- [ ] Temperatura: reparar el relé de estado sólido, contrastar la escala con termómetro y casos de evaluación
- [ ] Caudal: resolver el conflicto de IP `.10` (segmento aparte o enlace 1 del CP243-1)
- [ ] Orquestación multiagente sobre los cuatro equipos
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
| cFP / FieldPoint | Familia de controladores modulares de National Instruments con LabVIEW Real-Time |
| NI-PSP | Protocolo propietario de NI para variables compartidas en red |
| DataSocket | Componente ActiveX de NI que lee variables NI-PSP/FieldPoint por URL (`psp://`, `fieldpoint://`) |
| MAX | Measurement & Automation Explorer: configura controladores y E/S de NI |
| MQTT | Protocolo de mensajería publicar/suscribir |
| UNS | Unified Namespace: jerarquía común de datos industriales |
| MCP | Model Context Protocol: estándar para conectar LLM con herramientas y contexto |
| `.lvm` | Formato de medición de LabVIEW usado por los SCADA originales |
| Edge | Componente que corre junto al equipo y traduce sus datos al UNS |
