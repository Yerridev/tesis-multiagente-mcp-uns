# Red del laboratorio PLC Siemens S7-200

*Actualizado: 19-oct-2026*

## Equipos y direcciones IP

| Equipo | Dirección IP | Función |
|---|---|---|
| PLC Siemens S7-200 CPU 226 + CP243-1 Ethernet | `192.168.114.7` | Control del proceso; comunicación Ethernet por el CP243-1 (puerto TCP 102). |
| PLC Allen-Bradley MicroLogix 1100 (1763-LEC) + 1762-IF2OF2 | `192.168.114.9` | Módulo de nivel MCN-09; EtherNet/IP (PCCC) puerto TCP 44818, lectura con `pycomm3`. |
| Laptop de tesis (Windows 11) | `192.168.114.10` (IP adicional en el mismo adaptador) | Conector edge, Mosquitto, Docker (TimescaleDB, ingestor, Grafana), servidor MCP. Mantiene otra IP para internet. |
| PC del laboratorio (Windows XP, LabVIEW + PC Access) | `192.168.114.70` | SCADA original de Inducontrol; usa el enlace 0 del CP243-1. |
| PC/pantalla HMI | `192.168.114.72` | Visualización y control existente del proceso. |
| Máquina virtual Windows 7 (VirtualBox) | `192.168.114.30` | STEP 7-Micro/WIN y S7-200 PC Access por USB/PPI (diagnóstico). |

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
                    │      └─ enlace 1 ◄── Laptop de tesis:       192.168.114.10
                    └── PC / pantalla HMI:    192.168.114.72

Conexión adicional (diagnóstico): VM Windows 7 ── USB/PPI ── PLC S7-200
```

## Estado actual

- **Laptop ↔ PLC por Ethernet: operativo.** `python-snap7` lee las áreas V, M, I y Q por el enlace 1 (TSAP 11.00). El intento anterior fallaba porque la laptop no tenía la IP `.10` que el enlace 1 exige.
- **Limitación conocida:** el CP243-1 rechaza leer AIW/AQW directamente (error 0x03). Se leen sus copias en memoria: AIW0 → MW3, AIW2 → MW2, AQW0 ← MW25, AQW2 ← VW8.
- **PLC ↔ HMI y PLC ↔ PC del laboratorio:** operación existente; no se tocan.

> **Regla:** no modificar el programa del PLC, la configuración del CP243-1 ni la HMI. Toda la integración es de solo lectura.
