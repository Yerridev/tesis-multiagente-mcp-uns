# Módulo de control de nivel MCN-09/001 — MicroLogix 1100

Segundo equipo integrado a la arquitectura de la tesis. Es un módulo didáctico de **Inducontrol Ingeniería S.A.C.** (manual de 2006/2009) del Laboratorio de Automatización y Simulación de Procesos de la USS.

> **Regla del proyecto:** integración **solo lectura**. Ningún script de esta carpeta ni el conector escribe en el PLC (no existe ninguna llamada a `plc.write`).

*Actualizado: 20-oct-2026 — mapa v0.2, calibración de nivel y contraste con el manual del fabricante.*

## 1. Equipo y proceso

```text
        ┌──────── sensor ultrasónico Senix TS-30S1 (N7:4)
        ▼
   ┌─────────┐  T2: acrílico, 43 L, 60 cm (tanque controlado; rango de trabajo 0-35 cm)
   │   T2    │
   └────┬────┘  válvula Belimo LRB24-3 + válvula manual de salida → vuelve a T1
        │
   ┌────┴──────────────┐  T1: acero, 78 L (reserva) con interruptores Kobold NKP de nivel bajo/alto
   │        T1         │
   └───────────────────┘
        ▲ bomba Pentax Ultra U5 120/3T + variador Altivar 11 (velocidad por potenciómetro en LOCAL)
```

| Elemento | Detalle |
|---|---|
| PLC | Allen-Bradley **MicroLogix 1100** (`1763-LEC`) + **1762-IF2OF2** |
| Comunicación | Ethernet integrado, **EtherNet/IP (PCCC)**, TCP 44818, IP `192.168.114.9` |
| Tablero | Pilotos SISTEMA ENERGIZADO, SISTEMA FUNCIONANDO, ALARMA NIVEL ALTO y ALARMA NIVEL BAJO; potenciómetro CONTROL MANUAL; pulsadores ARRANQUE y PARADA MANUAL; selector LOCAL–0–REMOTO; paro de emergencia |
| HMI / SCADA originales | NI TPC-2106T (LabVIEW 8.6) + SCADA LabVIEW en PC. **No operativos** (ver §5) |

## 2. Cómo se obtuvo el mapa

1. **Backup del laboratorio:** proyecto LabVIEW, librería de variables, ~50 `.lvm` históricos y hojas técnicas.
2. **Programa RSLogix 500** (`upload final.RSS`), extraído sin RSLogix con `extract_rss.py`.
3. **Lectura en vivo:** `probe_ml1100.py` y `scan_ml1100.py`, que dan el directorio real de archivos de datos.
4. **Pruebas en marcha** (19 y 20-oct-2026): arranque, parada, selector, potenciómetro y llenado/vaciado.
5. **Calibración** del nivel en 4 puntos medidos con regla en T2.
6. **Contraste con el manual del fabricante** (43 páginas, fotografiado).

Detalle completo: [`tags_nivel.yaml`](tags_nivel.yaml).

## 3. Calibración del nivel

| Altura en T2 | `N7:4` | Recta | Error |
|---|---|---|---|
| 0 cm | 16 220 | 16 348 | 0,3 cm |
| 15 cm | 10 540 | 10 348 | 0,5 cm |
| 30 cm | 4 390 | 4 347 | 0,1 cm |
| 39 cm | 640 | 747 | 0,3 cm |

**`nivel_cm = (16348 − N7:4) / 400`**

- El sensor mide distancia, así que `N7:4` baja cuando el tanque se llena.
- **Satura cerca de 40–41 cm**, aunque T2 mide 60 cm.
- El rango de trabajo del fabricante es **0–35 cm**.
- El ultrasónico produce picos de eco con agua turbulenta. Por eso `nivel/cm` usa una mediana de 3 muestras.

## 4. Variables

| Variable UNS | Dirección | Estado |
|---|---|---|
| `nivel/raw`, `nivel/cm`, `nivel/pct`, `nivel/fuera_rango_sensor` | `N7:4` | confirmado |
| `bomba/potenciometro_raw` | `I:1.5`* | confirmado |
| `bomba/frecuencia_estimada_hz` | `I:1.5` × 0,00195 | hipótesis (2 puntos) |
| `estado/selector_remoto` / `estado/selector_local` | `I:0/0` / `I:0/1` | confirmado (centro = ambos en 0) |
| `estado/tanque1_con_agua` | `I:0/2` | confirmado (nivel bajo de T1 → para la bomba) |
| `estado/alarma_nivel_bajo_tanque1` | `O:0/1` | confirmado |
| `estado/pulsador_arranque` | `I:0/4` | confirmado |
| `estado/bomba_marcha`, `estado/piloto_marcha` | `O:0/2`, `O:0/3` | confirmado |
| `valvula/abriendo` + `valvula/t_apertura` | `O:0/4` + `T4:0` | confirmado (35 s al entrar en modo) |
| `estado/mando_i03` / `estado/piloto_o00` | `I:0/3` / `O:0/0` | hipótesis: nivel ALTO de T1 y su piloto |
| `estado/entrada_5` | `I:0/5` | hipótesis: paro de emergencia (NC) |
| `pid/*`, `valvula/*_sp` | `N7:1–14` | hipótesis (estáticos sin HMI) |

\* Dirección tal como la resuelve `pycomm3`.

La PARADA MANUAL detiene la bomba (confirmado), pero su entrada no se identificó: es un pulso de menos de 1 s.

## 5. Por qué el HMI y el SCADA no funcionan

Según el manual (p. 11), el **HMI se comunica directamente con el PLC por Ethernet** y es el controlador principal. La PC solo manda si el HMI le cede el control.

- El HMI **enciende y ejecuta su aplicación**, pero el proyecto LabVIEW lo tiene en `192.168.1.110`, mientras que el PLC está en `192.168.114.9` (otra subred).
- **Causa probable:** cambio de direccionamiento del PLC, lo que deja al HMI sin comunicación.
- **Consecuencia:** el modo REMOTO (PID) no recibe setpoint ni parámetros. Solo opera el modo LOCAL.
- Corregirlo implica modificar el PLC o el HMI, lo que queda **fuera del alcance** de la tesis (solo lectura).

## 6. Diferencias encontradas en el manual

El manual tiene errores copiados del módulo de caudal: "Sensor/Transmisor de Caudal", "0–35 l/min", "2 módulos de salida analógica" y "sensor 15–400 cm". Se priorizan las mediciones y las fichas técnicas de cada componente.

La ficha de la válvula Belimo indica **95 s** de carrera, pero el PLC la acciona **35 s**. Lo más probable es que la apertura "total" del arranque sea en realidad parcial.

## 7. Scripts

| Script | Función |
|---|---|
| `probe_ml1100.py` | Prueba inicial de comunicación |
| `scan_ml1100.py` | Mapa completo de archivos de datos; `--watch N` muestra solo los cambios |
| `extract_rss.py` | Extrae lógica y texto de un `.RSS` de RSLogix 500 |
| `../historiador/conector_edge_ml1100.py` | **Conector productivo v0.2** PLC → MQTT (UNS), ya calibrado |
| `../historiador/mcp_servidor/servidor_mcp_nivel.py` | **Servidor MCP** de solo lectura para agentes de IA |
| `../historiador/db/05_nivel_v02.sql` | Migración: renombra variables v0.1, recalcula `nivel/cm` y carga el rango 0–35 cm |

## 8. Servidor MCP `nivel-mcn09`

| Herramienta | Qué responde |
|---|---|
| `listar_variables` | Variables del módulo con dirección, unidad, estado y último dato |
| `obtener_lectura` | Último valor con **VIGENTE / DESACTUALIZADO** |
| `obtener_estado_plc` | Enlace, modo, bomba, nivel y tendencia, potenciómetro, válvula, T1 y alarmas |
| `consultar_historial` | Estadísticas y serie resumida (`uns` o `lvm`) |
| `comparar_con_rango` | Contraste con 0–35 cm (rango del fabricante, falta validar en el laboratorio) |
| `diagnosticar_nivel` | Diagnóstico por reglas: LLENANDO, NIVEL_ESTABLE, BOMBA_DETENIDA, TANQUE1_NIVEL_BAJO, REMOTO_SIN_SUPERVISOR… con tendencia en cm/min y **caudal neto estimado** (0,717 L/cm). Con `momento` reproduce un instante pasado. |

```powershell
cd ..\historiador
$env:MCP_DSN = "postgresql://mcp_lector:TU_CLAVE_LECTOR@localhost:5432/uns"
python mcp_servidor\servidor_mcp_nivel.py --probar
```

Para conectarlo a Claude Desktop, usa el bloque `nivel-mcn09` de `mcp_servidor/claude_desktop_config.ejemplo.json`.

## 9. Pendientes

- [ ] Confirmar `I:0/3` / `O:0/0` (nivel alto de T1) e `I:0/5` (emergencia) cuando ocurran.
- [ ] Más puntos para la frecuencia del variador.
- [ ] Importar los `.lvm` históricos de nivel (2008–2012).
- [ ] Grafo de conocimiento y dashboard de Grafana para nivel.
- [ ] Rango operativo validado por el responsable del laboratorio.
