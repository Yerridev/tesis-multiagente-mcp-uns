# Conectores del stack MCP-INDUSTRIAL (host)

Los tres equipos del laboratorio se leen desde **esta PC** (no desde la VM LAB-AUTOMATIZACION):

| Conector | Equipo | Transporte | Publica en |
|---|---|---|---|
| `launch_nivel_edge.ps1` | MicroLogix 1100 `192.168.114.9` | pycomm3 (TCP 502) | `127.0.0.1:1883` (broker Windows) |
| `launch_caudal_edge.ps1` | S7-200 `192.168.114.7` | snap7 ISO-TCP, **TSAP 1000** | `127.0.0.1:1883` |
| `launch_presion_edge.ps1` | NI cFP-2200 `192.168.114.8` | **DataSocket `psp://`** | `192.168.114.70:1884` (broker Docker) |
| `launch_presion_control.ps1` | cFP-2200 (escritura) | **DataSocket `psp://`** | `192.168.114.70:1884` |

`mirror-tesis` copia el broker Windows (1883) al broker Docker, por eso caudal y nivel llegan igual.

## Presión: por qué NO usa la VM

El cFP-2200 (LabVIEW RT 8.6) publica sus variables de red con el protocolo **PSP**
(`psp://<cFP>/<libreria>/<variable>`). El DataSocket instalado con LabVIEW 2023+ (`nids.dll 26.3`)
**no incluye** ese protocolo ("Unrecognized Protocol"). La solución aplicada en el host:

1. Copiar el `nids.dll` **4.9.0f0** (de la VM, con PSP) + `nipspxts.dll` 4.9.1 a `C:\Users\KST\NI-DS\`.
2. Registrar la clase COM **por usuario** (sin admin):
   `HKCU\Software\Classes\CLSID\{A7C10FE5-E3FC-11D0-80E8-00A02454310A}\InprocServer32` -> `C:\Users\KST\NI-DS\nids.dll`
3. Instalar **Python 3.7 de 32 bits** en `C:\Python37-32` (el `nids.dll` 4.9 es 32 bits) con `pywin32` y `paho-mqtt==1.6.1`.

Con eso el host lee y escribe las variables del cFP-2200 sin la VM.

## Qué se puede escribir en el cFP-2200 (verificado 30-oct-2026)

- **SÍ**: `DATOS_PAC/INICIO_PC` (tomar el mando: arranca la bomba) y `DATOS_PAC/SALIR_PC` (ceder el mando: la detiene).
- **NO**: `pid/setpoint_pc`, `pid/Kp_PC`, `pid/Ti_PC`, `pid/Td_PC`, `pid/valvula_pc` -> los **publica** la app RT del
  cFP-2200 y cualquier escritura externa se pisa. La consigna y el PID se cambian desde el panel HMI TPC-2106T
  (`pid/SETPOINT_TPM`) o recompilando la app RT.

## Arranque automatico

`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MCP-INDUSTRIAL-conectores.cmd`
arranca los cuatro supervisores (cada uno reinicia su conector si se cae).

## Variables de red que importan

- PLC caudal `.7` y nivel `.9` deben estar **encendidos** (el CP243-1 del S7-200 solo admite **una** sesion S7:
  por eso caudal usa el mismo proceso para leer y escribir).
- El cFP-2200 `.8` **siempre** tiene que estar encendido (es el "PLC" de presion).
- Selector fisico de presion en **AUTOMATICO**: el gate del backend rechaza las ordenes si esta en MANUAL.
# Control de temperatura MCT-09

`conector_control_temperatura.py` no escribe salidas fisicas. En modo REAL solo
admite `%M30` (inicio/parada del lazo PC) y `%MW100` (setpoint 15--50 C), siempre
con selector PC, sin fallo de nivel y confirmacion por lectura posterior. Para
arrancarlo use `launch_temperatura_control.ps1` **despues de cerrar TwidoSuite**;
Twido tiene pocas conexiones Modbus disponibles.

