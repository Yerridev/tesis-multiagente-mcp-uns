# Módulo de control de presión MCP-09/001 — NI Compact FieldPoint cFP-2200

Tercer equipo integrado a la arquitectura de la tesis. Es un módulo didáctico de **Inducontrol Ingeniería S.A.C.** (manual "MCP-09/001", copyright febrero 2008; programa LabVIEW de Corporación Córdova, 2008–2009) del Laboratorio de Automatización y Simulación de Procesos de la USS.

> **Regla del proyecto:** integración **solo lectura**. El conector abre DataSocket únicamente en modo lectura (`ReadAutoUpdate`) y no existe ninguna función de escritura hacia el cFP. No se modificó el programa del controlador; la recuperación del 21-oct-2026 restauró la configuración y el programa **originales** (ver [`RECUPERACION_cFP2200.md`](RECUPERACION_cFP2200.md)).

*Actualizado: 21-oct-2026 — equipo recuperado (parado desde 2018), conector v0.3, escala validada contra la HMI, servidor MCP v1.0.*

Documentos de esta carpeta:

| Documento | Contenido |
|---|---|
| `README.md` | Este documento: equipo, comunicación, variables, escala, conector, MCP y pendientes |
| [`RECUPERACION_cFP2200.md`](RECUPERACION_cFP2200.md) | Procedimiento paso a paso con el que se recuperó el controlador (repetible) |
| [`pruebas_20261021.md`](pruebas_20261021.md) | Bitácora de las pruebas en vivo del 21-oct-2026 con horas y valores |
| `prueba_manual_20261021.csv`, `prueba_remoto_20261021.csv` | Exportación de la base de las pruebas manual y remota |
| `probe_ni_vm.py`, `probe_ni_vm2.py`, `probe_ni_vm3.py` | Sondeos en la VM con los que se encontró la vía de lectura (OPC → DataSocket sin bombeo → DataSocket con bombeo COM); resultados resumidos en §3 |
| `herramientas/diag_cfp.py`, `herramientas/probe_cfp.py` | Diagnóstico por FTP y sondeo de puertos del cFP (solo lectura) |
| `puente_presion_VI.md` | **Descartado.** Puente LabVIEW en la PC XP; se reemplazó por DataSocket en la VM |

---

## 1. Equipo y proceso

```text
 T1 (recogida, 30,8 L) ──► BOMBA ──► T2 (CERRADO, 20,4 L) ──► válvula proporcional ──► retorno a T1
                            ▲                │
               variador Altivar 11     transmisor de presión 4-20 mA
                            ▲                │
                            └── cFP-2200 ◄───┘   (PID de LabVIEW Real-Time)
```

Al entrar agua al tanque cerrado T2 el aire se comprime y la presión sube. La **variable controlada** es la presión de T2; la **variable manipulada** es la velocidad de la bomba (variador). La válvula proporcional descarga T2 hacia T1 y sirve como **perturbación** (más apertura = menos presión). Rango de trabajo del manual: **3–40 psi** (con la válvula al 30 %).

| Elemento | Detalle |
|---|---|
| Controlador | **NI Compact FieldPoint cFP-2200** (PowerPC 400 MHz, 128 MB DRAM, VxWorks, LabVIEW Real-Time 8.6). N.º de serie `013DEF4C`, MAC `00:80:2F:11:76:97`, nombre de red `presion` |
| E/S | `cFP-DI-301 @1` (16 DI 24 V) · `cFP-DO-403 @2` (16 DO) · `cFP-AIO-610 @3` (4 AI ±20 mA, 4 AO 0–10 V) |
| Red | IP `192.168.114.8/24`, gateway `192.168.114.1`, time server `192.168.114.80` |
| Software en el cFP | FieldPoint 6.0.2 (julio 2008): LabVIEW RT 8.6, PID Control Toolkit 8.6, Network Variable Engine 1.5, Variable Client Support 1.5, Modbus I/O Server 1.5, DataSocket 4.5.5, NI-VISA 4.4, NI-Serial RT 3.3.2, NI-Watchdog 3.0, Web Server RT 1.0, Run-Time Engine for Web Services 1.0, System State Publisher 1.0. Bootrom **1.1.0** (30-jul-2007) |
| Programa | `startup.rtexe` (359 353 bytes) compilado del proyecto `MOD_PRESION.lvproj` (VI principal `DATOS_PRESION.vi`); publica las librerías de variables **`DATOS_PAC`** y **`pid`** |
| Transmisor | Danfoss **MBS 3000**, 0–6 bar, 4–20 mA (AIO-610 Input 0) |
| Bomba / variador | Bomba centrífuga Pentax Ultra U5 120/3T (1,2 HP) · variador Schneider **Altivar 11 `ATV11HU29M3A`** (1,5 kW, 200–240 V) |
| Válvula | Proporcional Danfoss **EV260B**, 0–10 V (AIO-610 Output 1) |
| Protecciones | Presostato Danfoss KPI (DI4), interruptores de nivel Kobold NKP en T1 (DI5 bajo, DI6 alto), válvula de alivio a 5 bar |
| Tablero | Pilotos SISTEMA FUNCIONANDO, ALARMA NIVEL ALTO, ALARMA NIVEL BAJO; perilla CONTROL MANUAL; pulsadores ARRANQUE y PARADA MANUAL; selector CONTROL LOCAL–REMOTO; paro de emergencia |
| HMI | NI **TPC-2106T** (Windows CE, `tp_presion.exe`), IP `192.168.114.82`. **Operativa**: muestra presión, SP, Hz y estados |
| SCADA | `PRESION.exe` (LabVIEW 8.6) en la PC Windows XP del laboratorio. **Operativo** (se usó en las pruebas remotas). Es la misma PC del SCADA de caudal (`.70`); se le puso temporalmente `.80` para presión y se devolverá a `.70` |
| Manómetro | **Averiado.** La referencia de presión es el transmisor (= HMI) |

## 2. Modos de operación (confirmados en las pruebas)

| Modo | Selector | Qué hace el programa | Velocidad de la bomba |
|---|---|---|---|
| **LOCAL** (manual) | `SEL_MANUAL` = 1 | ARRANQUE MANUAL enciende *SISTEMA FUNCIONANDO*, habilita el variador (`ACT_VARIADOR`) y abre la válvula a **5 V (50 %)** | La fija la **perilla frontal del Altivar** (salida AO0 = 0 V) |
| **REMOTO** (automático) | `SEL_AUTO` = 1 | Espera INICIO del supervisor (SCADA PC o HMI), que fija SP, Kp, Ti, Td y apertura de válvula. El PID escribe su salida 0–10 V en AO0 | **Debería** seguir al PID, pero hoy el Altivar la ignora (ver §7) |

## 3. Comunicación: por qué es distinto a caudal y nivel

| Equipo | Protocolo | ¿Librería abierta para Python? | Vía usada |
|---|---|---|---|
| S7-200 (caudal) | S7 / ISO-on-TCP | Sí (`python-snap7`) | Python directo |
| MicroLogix 1100 (nivel) | EtherNet/IP (PCCC) | Sí (`pycomm3`) | Python directo |
| **cFP-2200 (presión)** | **NI-PSP / Logos** (propietario de National Instruments, UDP) | **No** | **NI DataSocket (ActiveX) en la VM Windows 7 → Python** |

Sondeo de puertos TCP del cFP desde la laptop (`herramientas/probe_cfp.py`, 21-oct-2026): FTP 21 **abierto**, HTTP 80 **abierto** (sin respuesta útil), Modbus 502 **cerrado** (el Modbus I/O Server está instalado pero sin configurar), 2343 cerrado (NI-PSP usa UDP), Service Locator 3580 **abierto**, System Web Server 59110 **abierto**.

Opciones evaluadas:

| Opción | Resultado |
|---|---|
| Modbus TCP directo | Descartada: exige crear un I/O Server, enlazar variables y **recompilar `startup.rtexe`** (modifica el programa) |
| Puente LabVIEW en la PC XP (`puente_presion_VI.md`) | Descartada: la PC del laboratorio no puede usarse de forma permanente |
| Cambiar la laptop a `192.168.114.80` | No sirve: `.80` es solo el *time server* del cFP (sincroniza el reloj), el cFP no envía datos a esa IP; además habría conflicto de IP |
| **Driver NI-FieldPoint en la VM Windows 7 + DataSocket** | **Elegida.** Equivalente al esquema de PC Access de caudal; sin PC del laboratorio y sin tocar el cFP |

Hallazgos de las pruebas en la VM (`probe_ni_vm*.py`):
- El driver registra los servidores OPC DA `National Instruments.OPCFieldPoint` y `National Instruments.Variable Engine.1` y el ActiveX **`CWDSLib.CWDataSocket`**.
- DataSocket recibe los valores como **eventos COM**: hay que llamar a `pythoncom.PumpWaitingMessages()`; con `time.sleep()` solo se ve el 0 inicial (`status=5`). Con bombeo: `status=2` = conexión activa.
- Valores leídos: `FP/3AIO/00` = 0,004003 A · `DATOS_PAC/TRANS_PRESION` = 0,004003 · `DATOS_PAC/SEL_MANUAL` = True · `pid/Kp_PC` = 3,0.
- Funcionan tanto `psp://192.168.114.8/...` como `fieldpoint://192.168.114.8/FP/...`.

## 4. Variables

Variables compartidas del programa (`DATOS_PAC`, `pid`) y canales crudos FieldPoint (`FP/...`), tal como las publica el conector v0.3 en `uss/campus/lab-automatizacion/sl01la07/presion-mcp09/funcional/...`.

| Variable UNS | Origen en el cFP | Unidad | Estado | Nota |
|---|---|---|---|---|
| `presion/transmisor_ma` | `DATOS_PAC/TRANS_PRESION` | mA | confirmado | **El programa publica la corriente en A** (0,004 = 4 mA), no en psi |
| `presion/psi` | `DATOS_PAC/TRANS_PRESION` | psi | **confirmado** | `(mA − 4) / 16 × 87`, misma escala que la HMI (§5) |
| `presion/ai0_ma` | `FP/3AIO/00` | mA | confirmado | Canal crudo AIO-610 Input 0 (respaldo independiente del programa) |
| `bomba/potenciometro_ma` | `DATOS_PAC/POTENCIOMETRO` | mA | hipótesis | AIO-610 Input 3: ~0 con el sistema parado, ~3,05 en marcha; **no** gobierna la velocidad |
| `bomba/salida_variador` | `DATOS_PAC/VARIADOR` | V | confirmado | AO0: = salida del PID en REMOTO; 0 V en LOCAL |
| `valvula/salida` | `DATOS_PAC/VAL_PROPOR` | V | confirmado | AO1; 1 V = 10 % de apertura. LOCAL = 5 V |
| `estado/selector_remoto` | `DATOS_PAC/SEL_AUTO` | bool | confirmado | DI0 · selector CONTROL en REMOTO |
| `estado/selector_local` | `DATOS_PAC/SEL_MANUAL` | bool | confirmado | DI1 · selector CONTROL en LOCAL |
| `estado/pulsador_arranque` | `DATOS_PAC/ARRANQUE_MANUAL` | bool | confirmado | DI2 |
| `estado/pulsador_parada` | `DATOS_PAC/PARADA_MANUAL` | bool | hipótesis | DI3 (probablemente NC) |
| `estado/presostato` | `DATOS_PAC/PRESOS` | bool | hipótesis | DI4 |
| `estado/switch_nivel_bajo` / `estado/switch_nivel_alto` | `DATOS_PAC/SWITCH_NB` / `SWITCH_NA` | bool | hipótesis | DI5 / DI6 |
| `estado/sistema_funcionando` | `DATOS_PAC/LED_SIST_FUN` | bool | confirmado | DO0 |
| `estado/bomba_habilitada` | `DATOS_PAC/ACT_VARIADOR` | bool | confirmado | DO1 (orden de marcha al variador) |
| `estado/alarma_nivel_alto` / `estado/alarma_nivel_bajo` | `DATOS_PAC/LED_NA` / `LED_NB` | bool | confirmado | DO2 / DO3 |
| `pid/setpoint_pc` | `pid/setpoint_pc` | psi | confirmado | SP desde el SCADA (10, 15 y 20 psi en las pruebas) |
| `pid/setpoint_hmi` | `pid/SETPOINT_TPM` | psi | hipótesis | SP desde la HMI |
| `pid/cv` | `pid/salida_pid` | V | confirmado | Salida del PID 0–10 V (se satura en 10 V) |
| `pid/valvula_pc` | `pid/valvula_pc` | V | confirmado | Apertura desde el SCADA (3 = 30 %) |
| `pid/kp`, `pid/ti`, `pid/td` | `pid/Kp_PC`, `Ti_PC`, `Td_PC` | – | Kp confirmado | Valores vistos: Kp = 3, Ti = 0,1, Td = 0 (iguales a la HMI y a los `.lvm` de 2009) |

Mapa de E/S físico (de `i_o.xlsx` del backup): DI0 mando automático, DI1 mando manual, DI2 arranque, DI3 parada, DI4 presostato, DI5 switch nivel bajo, DI6 switch nivel alto · DO0 LED sistema funcionando, DO1 variador, DO2 LED nivel alto, DO3 LED nivel bajo · AI0 transmisor, AI3 potenciómetro · AO0 variador, AO1 válvula proporcional.

Configuración de canales en MAX (igual al `.iak` original de 2009): entradas AIO-610 **0 a 0,024 A**; salidas **0 a 10,2 V**, valor de encendido ≈ 0,002 V, watchdog deshabilitado.

## 5. Escala de presión

El manómetro del módulo está averiado, por lo que la escala se validó contra la **HMI TPC-2106T** del programa original durante la prueba manual del 21-oct-2026:

| HMI | Transmisor (base de datos) | `(mA − 4)/16 × 87` |
|---|---|---|
| 0,803 psi | ~4,148 mA | 0,80 psi ✓ |
| 0,919 psi | ~4,170 mA | 0,92 psi ✓ |

**`presion_psi = (mA − 4) / 16 × 87`** (transmisor 0–6 bar = 0–87 psi).

- En reposo el transmisor marca **4,02–4,035 mA** (offset de cero de ~0,1–0,2 psi).
- Con la válvula cerrada la presión **queda atrapada** en T2 aunque la bomba pare (1,77 psi a las 19:54).
- Pendiente: verificar con 2–3 puntos de un manómetro en buen estado.

## 6. Arquitectura de lectura

```text
cFP-2200 192.168.114.8 (NI-PSP)
      │  DataSocket ActiveX, solo lectura
      ▼
VM Windows 7 192.168.114.30 (VirtualBox) ── conector_edge_cfp2200.py v0.3 (Python 3.7.9 32 bits)
      │  MQTT → Mosquitto de la laptop 192.168.114.10:1883
      ▼
ingestor-presion (Docker, VAR_PREFIX=presion-mcp09/) → TimescaleDB → servidor_mcp_presion.py · Grafana · lienzo
```

### Preparación de la VM (una sola vez)
1. Instalar el driver **NI-FieldPoint** (descarga gratuita en ni.com; se recomendó la 6.0.11, la más cercana a la 6.0.2 del cFP). **Nunca aceptar en MAX "instalar/actualizar software" en el cFP.**
2. `pip install pywin32 paho-mqtt`.
3. Copiar `conector_edge_cfp2200.py` y `CONECTOR_CFP2200.bat` (de `historiador/`).
4. Que no aparezca el diálogo "Python has stopped working" (bloquearía el reinicio automático):
   `reg add "HKCU\Software\Microsoft\Windows\Windows Error Reporting" /v DontShowUI /t REG_DWORD /d 1 /f`
5. Arranque automático: `Win+R` → `shell:startup` → acceso directo a `CONECTOR_CFP2200.bat`.

### Preparación de la laptop (una sola vez)
La red Ethernet del laboratorio aparecía como "Red no identificada" en perfil **Público**, que bloquea el tráfico entrante desde la VM. En PowerShell como administrador:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Ethernet" -NetworkCategory Private
New-NetFirewallRule -DisplayName "ICMPv4 entrante" -Protocol ICMPv4 -IcmpType 8 -Direction Inbound -Action Allow
New-NetFirewallRule -DisplayName "Mosquitto 1883" -Protocol TCP -LocalPort 1883 -Direction Inbound -Action Allow
```

Mosquitto debe tener `listener 1883 0.0.0.0` y `allow_anonymous true`. Prueba desde la VM:
`python -c "import socket;socket.create_connection(('192.168.114.10',1883),3);print('MQTT OK')"`.

## 7. Hallazgo: el Altivar 11 no obedece al PID

En las dos pruebas en REMOTO (18:52 y 19:16) el PID llevó su salida de 0 a **10 V en ~21 s** y la mantuvo saturada varios minutos, pero la presión no siguió al setpoint (quedó en ~0,1 psi con la perilla del Altivar en 0, y en ~0,7–1,0 psi cuando la perilla estaba subida). En LOCAL la bomba solo respondió a la **perilla frontal del variador** (24,2 y 30,7 Hz).

- La orden de **marcha** sí llega (DO1 `ACT_VARIADOR` = 1 en ambas pruebas).
- La **consigna de velocidad** 0–10 V del cFP (AO0) **no**: el variador está tomando la referencia de su potenciómetro frontal. El modelo `ATV11HU29M3A` (sufijo "A") trae de fábrica el control local activo; probablemente quedó así tras un reset o un reemplazo.
- **Solución propuesta (fuera del alcance de solo lectura):** que el responsable del laboratorio configure el Altivar para tomar la consigna por **AI1 (0–10 V)** y revise el cableado de la perilla CONTROL MANUAL. En el primer arranque remoto usar setpoint bajo (~5 psi) y Ti mayor.
- El servidor MCP detecta esta situación como **`ACTUADOR_NO_RESPONDE`** (PID ≥ 9,5 V durante ≥ 20 s, error > 2 psi y presión sin subir).

## 8. Servidor MCP `presion-mcp09`

`historiador/mcp_servidor/servidor_mcp_presion.py` (rol `mcp_lector`, sesiones read-only, sin ruta hacia el cFP).

| Herramienta | Qué responde |
|---|---|
| `listar_variables` | Variables con origen en el cFP, unidad, estado (confirmado/hipótesis) y último dato |
| `obtener_lectura` | Último valor con **VIGENTE / DESACTUALIZADO** |
| `obtener_estado_plc` | Enlace, modo, marcha, presión y tendencia, setpoint activo, salida PID, válvula %, Kp/Ti/Td y alarmas |
| `consultar_historial` | Estadísticas y serie resumida |
| `comparar_con_rango` | Contraste con **3–40 psi** (rango del fabricante; falta validación del laboratorio) |
| `diagnosticar_presion` | `SIN_DATOS`, `SELECTOR_EN_0`, `SISTEMA_DETENIDO`, `MANUAL_EN_MARCHA`, `REMOTO_SIN_SETPOINT`, **`ACTUADOR_NO_RESPONDE`**, `SUBIENDO_A_SETPOINT`, `EN_SETPOINT`, `SOBRE_SETPOINT`, `FUERA_DE_SETPOINT`; con `momento` reproduce un instante pasado |
| `consultar_grafo` | Grafo `conocimiento/grafo_mcp09.json` (14 nodos, 16 relaciones) |

Validación con datos reales (21-oct-2026): 18:30:30 → `MANUAL_EN_MARCHA` · 18:55:00 → `ACTUADOR_NO_RESPONDE` (149 s saturado) · 19:22:30 → `ACTUADOR_NO_RESPONDE` (358 s saturado, SP 15 psi) · 19:35 → `SIN_DATOS` (conector caído) · 19:37 → `SISTEMA_DETENIDO`.

```powershell
cd ..\historiador
.venv\Scripts\python mcp_servidor\servidor_mcp_presion.py --probar
```

## 9. Archivos del módulo en el repositorio

| Archivo | Función |
|---|---|
| `historiador/conector_edge_cfp2200.py` | Conector v0.3 DataSocket → MQTT (corre en la VM) |
| `historiador/CONECTOR_CFP2200.bat` | Lanza el conector y lo reinicia si se cierra (log en `conector_cfp2200_fallas.log`) |
| `historiador/db/06_presion_v01.sql` | Migración: renombra selectores, unidades en V y rango 3–40 psi |
| `historiador/docker-compose.yml` | Servicio `ingestor-presion` (prefijo `presion-mcp09/`) |
| `historiador/mcp_servidor/servidor_mcp_presion.py` | Servidor MCP v1.0 |
| `historiador/mcp_servidor/conocimiento/grafo_mcp09.json` | Knowledge graph |
| `historiador/mcp_servidor/conocimiento/equipos.json` | Registro del equipo para el lienzo y el agente |
| `historiador/grafana/dashboards/presion_mcp09.json` | Dashboard (8 paneles) |
| `historiador/iniciar_arquitectura.ps1` | Arranque v2: enciende la VM y espera el latido del conector de presión |

Historial de versiones del conector:
- **v0.1** — puente UDP desde un VI de LabVIEW en la PC XP (descartado, nunca se usó).
- **v0.2** — DataSocket directo desde la VM; 23 variables; escala hipotética.
- **v0.2 + ajustes** — escala confirmada contra la HMI; selectores renombrados a `selector_remoto/local`; unidades en V; catálogo con `dir`.
- **v0.3** — tras un cierre "Python has stopped working" (~19:42): reapertura de variables limitada a una vez cada 15 s y liberando el objeto anterior (antes creaba un ActiveX nuevo por segundo), reciclaje de conexiones cada 30 min y `faulthandler` en `conector_cfp2200_fallas.log`.

## 10. Respaldos (fuera del repositorio)

| Ubicación | Contenido |
|---|---|
| `Y:\Downloads\INFORMACION-ENCONTRADA-LABORATORIO\BACKUP-4PLCS\manual_presion.pdf` | Manual MCP-09/001 fotografiado (55 páginas) |
| `Y:\Downloads\INFORMACION-ENCONTRADA-LABORATORIO\BACKUP-4PLCS\LABVIEW PRESION\` | Proyectos `MOD_PRESION.lvproj` y `2026-presion`, `DATOS_PAC.lvlib`, `pid.lvlib`, `i_o.xlsx`, `DEPLOY\` (copia de `startup.rtexe` y `data\`), `EXE\PRESION.exe`, `TPMEXE\tp_presion.exe`, `installer\`, históricos `historico_p_pc\*.lvm` (2008–2009) |
| `Y:\Downloads\BACKUP_cFP2026-10-21\` | **Copia FTP completa del cFP antes del formateo** (`ni-rt.ini`, `ni-rt\startup`, `ni-rt\system`, `tmp` con logs 2012–2018) |
| `Y:\Downloads\DIAG_cFP_20261021_1316\`, `..._1440\` | Diagnósticos FTP después de la reinstalación y después de restaurar el programa |

Formato de los `.lvm` históricos (8 columnas, 1 muestra/s), deducido de los valores: setpoint (psi) · presión medida (psi) · salida PID (0–10) · válvula (0–10) · Kp · Ti · Td · modo. Pendiente de importar (falta escribir el script, como el de caudal).

## 11. Pendientes

- [ ] **Altivar 11:** consigna por AI1 (0–10 V) con el responsable del laboratorio; luego repetir la prueba remota (SP 5 → 10 → 20 psi) y medir respuesta del lazo.
- [ ] Verificar la escala con un manómetro en buen estado (2–3 puntos).
- [ ] Confirmar presostato, switches de nivel y PARADA (NC) cuando ocurran.
- [ ] Unidad real de `POTENCIOMETRO` y cableado de la perilla CONTROL MANUAL.
- [ ] Importar los `.lvm` de `historico_p_pc` (2008–2009).
- [ ] Casos de evaluación de presión en `evaluacion/reproducir_casos.py`.
- [ ] Rango operativo validado por el responsable del laboratorio (hoy 3–40 psi del fabricante).
- [ ] Revisar `conector_cfp2200_fallas.log` si el conector vuelve a cerrarse.
- [ ] Dejar el switch CONS. OUT del cFP en OFF y desconectar el cable null-modem.
