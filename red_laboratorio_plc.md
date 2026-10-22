# Red del laboratorio (caudal, nivel y presión)

*Actualizado: 21-oct-2026 (se agrega el módulo de presión cFP-2200, la VM como conector y la configuración de firewall de la laptop)*

## Equipos y direcciones IP

| Equipo | Dirección IP | Función |
|---|---|---|
| PLC Siemens S7-200 CPU 226 + CP243-1 Ethernet | `192.168.114.7` | Módulo de caudal MCC-09. Comunicación Ethernet por el CP243-1 (puerto TCP 102), lectura con `python-snap7`. |
| NI Compact FieldPoint **cFP-2200** (nombre de red `presion`) | `192.168.114.8` | Módulo de presión MCP-09/001. Variables compartidas NI-PSP (UDP); FTP 21 abierto; Modbus 502 cerrado. Lectura con DataSocket desde la VM. Gateway `192.168.114.1`, time server `192.168.114.80`. Ver [`presion/README.md`](presion/README.md). |
| PLC Allen-Bradley MicroLogix 1100 (1763-LEC) + 1762-IF2OF2 | `192.168.114.9` | Módulo de nivel MCN-09; EtherNet/IP (PCCC) puerto TCP 44818, lectura con `pycomm3`. |
| Laptop de tesis (Windows 11) | `192.168.114.10` (IP adicional en el mismo adaptador) | Conectores de caudal y nivel, Mosquitto, Docker (TimescaleDB, ingestores, Grafana, lienzo), servidores MCP. Mantiene otra IP para internet. |
| Equipo anfitrión de la VM | `192.168.114.11` (observada por ping desde la VM) | PC real donde corre VirtualBox. |
| Máquina virtual Windows 7 (VirtualBox, red en puente) | `192.168.114.30` | **Conector de presión** `conector_edge_cfp2200.py` (driver NI-FieldPoint + DataSocket, Python 3.7 32 bits). También STEP 7-Micro/WIN y S7-200 PC Access por USB/PPI (diagnóstico del S7-200). |
| PC del laboratorio (Windows XP, LabVIEW 8.6 + PC Access + MAX) | `192.168.114.70` (IP original) · `192.168.114.80` (temporal) | **Un solo equipo.** Con `.70`: SCADA de caudal por el enlace 0 del CP243-1. Para el módulo de presión se le cambió temporalmente a `.80` (es la única PC con LabVIEW 8.6; `.80` es también el *time server* configurado en el cFP): SCADA `PRESION.exe`, MAX, HyperTerminal y despliegue de variables en la recuperación. **Se devolverá a `.70`**, como se encontró en el laboratorio. |
| PC/pantalla HMI | `192.168.114.72` | Visualización y control existente del proceso de caudal. |
| HMI NI TPC-2106T (presión) | `192.168.114.82` | Pantalla táctil del módulo de presión (`tp_presion.exe`); operativa. |

## Enlaces del CP243-1 (configuración existente, no modificar)

| Enlace | Rol | TSAP local/remoto | Cliente autorizado | Uso actual |
|---|---|---|---|---|
| 0 | Servidor | `10.00 / 10.00` | `192.168.114.70` | SCADA LabVIEW de la PC del laboratorio |
| 1 | Servidor | `11.00 / 11.00` | `192.168.114.10` | **Conector edge de la tesis (solo lectura)** |

## Esquema general

```text
                RED LOCAL 192.168.114.0/24
                          │
                    SWITCH ETHERNET
                    ├── PLC S7-200 + CP243-1: 192.168.114.7
                    │      ├─ enlace 0 ◄── PC laboratorio (XP):   192.168.114.70
                    │      └─ enlace 1 ◄── Laptop de tesis:       192.168.114.10  (snap7)
                    ├── cFP-2200 presión:    192.168.114.8
                    │      ├─ NI-PSP ◄── PC laboratorio (XP) SCADA: 192.168.114.80 (temporal; misma PC que .70)
                    │      ├─ NI-PSP ◄── HMI TPC-2106T:           192.168.114.82
                    │      └─ NI-PSP ◄── VM Windows 7:            192.168.114.30  (DataSocket)
                    │                        └─ MQTT ──► Mosquitto laptop .10:1883
                    ├── MicroLogix 1100 nivel: 192.168.114.9 ◄── Laptop .10 (pycomm3)
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

## Estado actual

- **Laptop ↔ S7-200 por Ethernet: operativo.** `python-snap7` lee las áreas V, M, I y Q por el enlace 1 (TSAP 11.00).
- **Limitación conocida del CP243-1:** rechaza leer AIW/AQW directamente (error 0x03). Se leen sus copias en memoria: AIW0 → MW3, AIW2 → MW2, AQW0 ← MW25, AQW2 ← VW8.
- **Laptop ↔ MicroLogix 1100: operativo** (`pycomm3`, PCCC).
- **VM ↔ cFP-2200: operativo** (DataSocket, solo lectura) desde el 21-oct-2026; **VM → Mosquitto de la laptop: operativo** tras el cambio a perfil Privado.
- **PLC ↔ HMI y PLC ↔ PC del laboratorio:** operación existente; no se tocan.
- **Nota sobre la PC XP:** mientras tenga `.80`, el SCADA de caudal no puede usar el enlace 0 del CP243-1 (exige `.70`); al volver a `.70`, el cFP pierde su *time server* (solo afecta la hora del reloj del cFP, no la lectura de datos). La lectura de la tesis no depende de esta PC en ningún caso.
- El script `INICIAR_TODO.bat` / `historiador/iniciar_arquitectura.ps1` (v2) hace ping a `.7`, `.8` y `.9` y arranca solo los conectores de los equipos encendidos; para presión enciende la VM (nombre en `VM_PRESION` del `.env`) y espera su latido MQTT.

> **Regla:** no modificar los programas de los controladores, la configuración del CP243-1, el Altivar ni las HMI. Toda la integración es de solo lectura.
