# Módulo de control de nivel MCN-09/001 — MicroLogix 1100

Segundo equipo integrado a la arquitectura de la tesis. Módulo didáctico de **Inducontrol Ingeniería S.A.C.** (2006) del Laboratorio de Automatización y Simulación de Procesos de la USS.

> **Regla del proyecto:** integración **solo lectura**. Ningún script de esta carpeta escribe en el PLC (no existe ninguna llamada a `plc.write`).

## 1. Equipo

| Elemento | Detalle |
|---|---|
| PLC | Allen-Bradley **MicroLogix 1100** (catálogo reportado: `1763-LEC`) |
| Expansión analógica | **1762-IF2OF2** (2 entradas / 2 salidas analógicas) |
| Comunicación | Puerto Ethernet integrado, **EtherNet/IP (PCCC)**, TCP 44818 |
| IP | `192.168.114.9` |
| Sensor de nivel | Ultrasónico **TS-30S** (mide **distancia** a la superficie del agua) |
| Bomba | Pentax Ultra 7 con variador **Schneider Altivar 11** |
| Válvula | **Belimo LRB24-3** (actuador flotante: abrir/cerrar por tiempo) |
| HMI / SCADA originales | NI TPC-2106T + SCADA LabVIEW 8.6 (`NIVEL.exe`), hoy **no operativos** |

## 2. Cómo se obtuvo el mapa de variables

1. **Backup del laboratorio** (`BACKUP-4PLCS\INDUCONTROL NIVEL`): proyecto LabVIEW `MCN.lvproj`, librería de variables `Libreria_hmi.lvlib`, ~50 históricos `.lvm` (2008–2012), hojas técnicas y guías de práctica.
2. **Proyecto RSLogix 500** `upload final.RSS`: se extrajo sin RSLogix con `extract_rss.py` (contenedor OLE + streams zlib). La lógica ladder permitió identificar direcciones, el PID `PD12:0`, los temporizadores de la válvula y los escalados.
3. **Lectura en vivo** con `probe_ml1100.py` y `scan_ml1100.py` (directorio real de archivos de datos del procesador).
4. **Prueba en marcha manual** (19-oct-2026) con `scan_ml1100.py --watch 2`: arranque/paro de bomba, llenado y apertura de válvula.

### Archivos de datos reales del procesador

| Archivo | Elementos | Uso |
|---|---|---|
| `B3` | 11 | Bits internos (modos, marcha, alarmas) |
| `T4` | 11 | Temporizadores (válvula `T4:0`/`T4:1` base 0,01 s; `T4:2`, `T4:3` base 1 s) |
| `C5` | 1 | Contador |
| `R6` | 1 | Control |
| `N7` | 21 | Enteros: nivel, setpoints, parámetros PID, límites de salida |
| `F8` | 10 | Flotantes (`F8:4..6` = 3,0 / 0,1 / 0,01) |
| `PD12` | 1 | Bloque PID |

## 3. Variables identificadas

Detalle completo en [`tags_nivel.yaml`](tags_nivel.yaml).
**Confirmado** = visto en vivo y coherente con la lógica. **Hipótesis** = deducido, falta prueba dirigida.

| Variable | Dirección | Estado | Observación |
|---|---|---|---|
| Nivel (crudo) | `N7:4` | confirmado | PV del PID. **Inverso:** baja al llenar (el sensor mide distancia). Rango visto 11104–16536 |
| Velocidad bomba (cruda) | `I:1.5`* | hipótesis | ~9000 en marcha, 0 parada |
| Consigna PLC → variador | `O:1.0` | confirmado | 0 en modo manual (el potenciómetro manda directo) |
| Bomba en marcha | `O:0/2`, `O:0/3` | confirmado | |
| Válvula abrir | `O:0/4` + `T4:0` | confirmado | Carrera 35 s (`PRE` 3500 × 0,01 s) |
| Válvula cerrar | `O:0/5` + `T4:1` | hipótesis | |
| Selector del tablero | `I:0/0` ↔ `I:0/1` | hipótesis | Posible Local/Remoto |
| Setpoints | `N7:5`, `N7:6` | hipótesis | Se copian a `PD12:0.SPS` según el modo |
| Kc, Ti, Td | `N7:8–10`, `N7:11–13` | hipótesis | Dos juegos, seleccionados por `B3:0/3` |
| CV del PID | `N7:14` | hipótesis | Escalado en `N7:20` hacia `O:1.0` |
| Tiempos de válvula (SP) | `N7:1`, `N7:2` | hipótesis | → `T4:0.PRE`, `T4:1.PRE` en modo remoto |

\* Dirección tal como la resuelve `pycomm3`.

## 4. Por qué el HMI y el SCADA originales no funcionan

Según `MCN.lvproj` y `MCN.aliases`, la arquitectura original era **PLC ↔ PC SCADA (`192.168.114.90`, LabVIEW) ↔ HMI TPC-2106T**. Las variables compartidas que lee el HMI se publicaban desde esa PC. En modo remoto, el PLC espera que la PC escriba setpoints y parámetros en `N7`. Sin esa PC, solo opera el **modo manual**: potenciómetro → variador.

Revivir el SCADA implicaría escribir en el PLC, lo que queda **fuera del alcance** de la tesis.

## 5. Scripts

| Script | Función |
|---|---|
| `probe_ml1100.py` | Primera prueba: TCP 44818, tipo de procesador y lectura de bloques básicos |
| `scan_ml1100.py` | Descubre los archivos de datos y su tamaño, lee todo, guarda `mapa_ml1100_*.json`. Con `--watch N` muestra solo lo que cambia |
| `extract_rss.py` | Extrae texto y lógica de un `.RSS` de RSLogix 500 (sin RSLogix) → `rss_dump.txt` |
| `../historiador/conector_edge_ml1100.py` | **Conector productivo** PLC → MQTT (UNS) |

```powershell
pip install pycomm3 olefile paho-mqtt
python scan_ml1100.py                 # mapa completo
python scan_ml1100.py --watch 2       # cambios en vivo
python extract_rss.py "Y:\Downloads\upload final.RSS"
```

## 6. Integración con el historiador

- **Tópico base UNS:** `uss/campus/lab-automatizacion/sl01la07/nivel-mcn09`
- **Ingestor:** servicio `ingestor-nivel` en `historiador/docker-compose.yml`. Guarda con prefijo `nivel-mcn09/` (por ejemplo `nivel-mcn09/nivel/raw`) para no mezclarse con caudal.

```powershell
cd ..\historiador
python conector_edge_ml1100.py                                         # sin calibrar: publica nivel/raw
python conector_edge_ml1100.py --raw-vacio <N7:4 vacío> --raw-lleno <N7:4 lleno>   # agrega nivel/pct
```

## 7. Pendientes

- [ ] Calibración de nivel en 2 puntos (tanque bajo / alto) → `--raw-vacio`, `--raw-lleno`.
- [ ] Confirmar `I:1.5` girando el potenciómetro con la bomba en marcha.
- [ ] Confirmar el significado de `I:0/0`–`I:0/5` y de los bits de `B3`.
- [ ] Importar los `.lvm` históricos de nivel (mapa de canales por confirmar).
- [ ] Servidor MCP `nivel-mcn09` (listar_variables, obtener_lectura, consultar_historial, obtener_estado_plc, comparar_con_rango).
- [ ] Rango operativo validado por el responsable del laboratorio.
