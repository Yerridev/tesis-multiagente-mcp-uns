# Red del laboratorio (caudal, nivel, presión y temperatura)

*Actualizado: 23-oct-2026 (se agrega el módulo de temperatura con PLC Twido en `.10`; la laptop de tesis pasa a `.12`). Anterior: 21-oct-2026 (módulo de presión, VM conector y firewall de la laptop)*

## Equipos y direcciones IP

| Equipo | Dirección IP | Función |
|---|---|---|
| PLC Siemens S7-200 CPU 226 + CP243-1 Ethernet | `192.168.114.7` | Módulo de caudal MCC-09. Comunicación Ethernet por el CP243-1 (puerto TCP 102), lectura con `python-snap7`. |
| NI Compact FieldPoint **cFP-2200** (nombre de red `presion`) | `192.168.114.8` | Módulo de presión MCP-09/001. Variables compartidas NI-PSP (UDP); FTP 21 abierto; Modbus 502 cerrado. Lectura con DataSocket desde la VM. Gateway `192.168.114.1`, time server `192.168.114.80`. Ver [`presion/README.md`](presion/README.md). |
| PLC Allen-Bradley MicroLogix 1100 (1763-LEC) + 1762-IF2OF2 | `192.168.114.9` | Módulo de nivel MCN-09; EtherNet/IP (PCCC) puerto TCP 44818, lectura con `pycomm3`. |
| PLC Schneider Twido TWDLCAE40DRF + 2× TWDAMM3HT | `192.168.114.10` | Módulo de temperatura MCT-09/001. **IP fija en la configuración del PLC (no se cambia).** Modbus TCP puerto 502 (%MW = holding registers, %M = coils, base 0). |
| Laptop de tesis (Windows 11) | `192.168.114.12` (IP adicional en el mismo adaptador; fue `.10` hasta el 23-oct-2026) | Conectores de caudal y nivel, Mosquitto, Docker (TimescaleDB, ingestores, Grafana, lienzo), servidores MCP. Mantiene otra IP para internet. |
| Equipo anfitrión de la VM | `192.168.114.11` (observada por ping desde la VM) | PC real donde corre VirtualBox. |
| Máquina virtual Windows 7 (VirtualBox, red en puente) | `192.168.114.30` | **Conector de presión** `conector_edge_cfp2200.py` (driver NI-FieldPoint + DataSocket, Python 3.7 32 bits). También STEP 7-Micro/WIN y S7-200 PC Access por USB/PPI (diagnóstico del S7-200). |
| PC del laboratorio (Windows XP, LabVIEW 8.6 + PC Access + MAX) | `192.168.114.70` (IP original) · `192.168.114.80` (temporal) | **Un solo equipo.** Con `.70`: SCADA de caudal por el enlace 0 del CP243-1. Para el módulo de presión se le cambió temporalmente a `.80` (es la única PC con LabVIEW 8.6; `.80` es también el *time server* configurado en el cFP): SCADA `PRESION.exe`, MAX, HyperTerminal y despliegue de variables en la recuperación. **Se devolverá a `.70`**, como se encontró en el laboratorio. |
| PC/pantalla HMI | `192.168.114.72` | Visualización y control existente del proceso de caudal. |
| HMI NI TPC-2106T (presión) | `192.168.114.82` | Pantalla táctil del módulo de presión (`tp_presion.exe`); operativa. |
| PC del laboratorio (misma PC XP) para temperatura | `192.168.114.100` | SCADA `MOD_TEMP.exe` → DataSocket → Industrial Automation OPC Servers 5.1 (objeto Modbus `temp`, PollRate `0:01`) → Twido. Aloja las variables compartidas `LIB_PC`/`LIB_HMI` de la HMI. |
| HMI NI TPC-2106T (temperatura) | `192.168.114.101` | HMI del módulo de temperatura (`HMI_mct.exe`); habla con las variables compartidas de la PC `.100`, no con el PLC. |

## Enlaces del CP243-1 (configuración existente, no modificar)

| Enlace | Rol | TSAP local/remoto | Cliente autorizado | Uso actual |
|---|---|---|---|---|
| 0 | Servidor | `10.00 / 10.00` | `192.168.114.70` | SCADA LabVIEW de la PC del laboratorio |
| 1 | Servidor | `11.00 / 11.00` | `192.168.114.10` | **Conector edge de la tesis (solo lectura)**. ⚠️ La laptop ya no tiene `.10` (la ocupa el Twido): ver *Conflicto de IP* |

## Esquema general

```text
                RED LOCAL 192.168.114.0/24
                          │
                    SWITCH ETHERNET
                    ├── PLC S7-200 + CP243-1: 192.168.114.7
                    │      ├─ enlace 0 ◄── PC laboratorio (XP):   192.168.114.70
                    │      └─ enlace 1 ◄── cliente .10 (laptop de tesis hasta el 23-oct; hoy pendiente)
                    ├── cFP-2200 presión:    192.168.114.8
                    │      ├─ NI-PSP ◄── PC laboratorio (XP) SCADA: 192.168.114.80 (temporal; misma PC que .70)
                    │      ├─ NI-PSP ◄── HMI TPC-2106T:           192.168.114.82
                    │      └─ NI-PSP ◄── VM Windows 7:            192.168.114.30  (DataSocket)
                    │                        └─ MQTT ──► Mosquitto laptop .12:1883
                    ├── MicroLogix 1100 nivel: 192.168.114.9 ◄── Laptop .12 (pycomm3)
                    ├── Twido temperatura:   192.168.114.10
                    │      ├─ Modbus TCP ◄── PC laboratorio (XP) OPC Servers: 192.168.114.100 ◄── HMI TPC .101
                    │      └─ Modbus TCP ◄── Laptop .12 (conector de temperatura, solo lectura)
                    └── PC / pantalla HMI:    192.168.114.72

Conexión adicional (diagnóstico): VM Windows 7 ── USB/PPI ── PLC S7-200
Conexión de recuperación (21-oct): PC XP ── cable serial null-modem ── cFP-2200 (9600 8N1)
```

## Configuración de la laptop para recibir a la VM

La red Ethernet del laboratorio aparece como "Red no identificada" en perfil **Público**, que bloquea el tráfico entrante. Sin esto la VM hace ping al cFP y a su anfitrión, pero no a la laptop ni a Mosquitto. PowerShell como administrador (una vez):

```powershell
Set-NetConnectionProfile -InterfaceAlias "Ethernet" -NetworkCategory Private
New-NetFirewallRule -DisplayName "ICMPv4 entrante" -Protocol ICMPv4 -IcmpType 8 -Direction Inbound -Action Allow
New-NetFirewallRule -DisplayName "Mosquitto 1883" -Protocol TCP -LocalPort 1883 -Direction Inbound -Action Allow
```

## Conflicto de IP (23-oct-2026)

El Twido de temperatura tiene `192.168.114.10` fija en su configuración, que era la IP de la laptop de tesis. La laptop pasó a `192.168.114.12` y se actualizaron `CONECTOR_CFP2200.bat` (broker `.12`; **copiar el .bat nuevo a la VM**), `iniciar_arquitectura.ps1` y la documentación.

Consecuencia: **el conector de caudal no puede leer el S7-200**, porque el enlace 1 del CP243-1 solo acepta al cliente `.10`. Opciones (pendiente de decisión):

1. **Segmento aparte para temperatura** (no toca equipos): Twido `.10`, PC XP `.100` y HMI `.101` en otro switch; la laptop entra a ese switch con un adaptador USB-Ethernet (`.12`) y en la red principal vuelve a tener `.10`.
2. **Reconfigurar el enlace 1 del CP243-1** para aceptar `.12` (asistente Ethernet de STEP 7-Micro/WIN + descarga al PLC): requiere autorización, contradice la regla de no modificar.
3. ~~Cambiar la IP del Twido~~: descartado. El SCADA usa %M41/%M42, que no están en el respaldo `Twido1.xtwd`; el programa real del PLC es más nuevo que el respaldo y descargarlo podría borrar lógica.

## Estado actual

- **Laptop ↔ S7-200 por Ethernet: operativo.** `python-snap7` lee las áreas V, M, I y Q por el enlace 1 (TSAP 11.00).
- **Limitación conocida del CP243-1:** rechaza leer AIW/AQW directamente (error 0x03). Se leen sus copias en memoria: AIW0 → MW3, AIW2 → MW2, AQW0 ← MW25, AQW2 ← VW8.
- **Laptop ↔ MicroLogix 1100: operativo** (`pycomm3`, PCCC).
- **VM ↔ cFP-2200: operativo** (DataSocket, solo lectura) desde el 21-oct-2026; **VM → Mosquitto de la laptop: operativo** tras el cambio a perfil Privado.
- **PLC ↔ HMI y PLC ↔ PC del laboratorio:** operación existente; no se tocan.
- **Nota sobre la PC XP:** mientras tenga `.80`, el SCADA de caudal no puede usar el enlace 0 del CP243-1 (exige `.70`); al volver a `.70`, el cFP pierde su *time server* (solo afecta la hora del reloj del cFP, no la lectura de datos). La lectura de la tesis no depende de esta PC en ningún caso.
- El script `INICIAR_TODO.bat` / `historiador/iniciar_arquitectura.ps1` (v2) hace ping a `.7`, `.8` y `.9` y arranca solo los conectores de los equipos encendidos; para presión enciende la VM (nombre en `VM_PRESION` del `.env`) y espera su latido MQTT.

> **Regla:** no modificar los programas de los controladores, la configuración del CP243-1, los variadores ni las HMI. Toda la integración es de solo lectura. *Excepción registrada (23-oct-2026): Altivar 11 del módulo de temperatura pasado de mando local a bornes (`tCC=2C`, `AIt=10U`) para restituir el diseño original.*
