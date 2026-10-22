# Recuperación del cFP-2200 (módulo de presión MCP-09/001)

Procedimiento con el que se recuperó el controlador el **21-oct-2026** (estaba parado desde 2018). Sirve para repetirlo si vuelve a perder la IP, queda en *Safe Mode* o se borra el programa.

> **Regla:** se restauró la configuración y el programa **originales**. No se desplegó nada desde los proyectos `2026-presion` ni `q1` (copias de trabajo, no las versiones validadas del laboratorio).

## Síntoma inicial

- En LabVIEW RT el CPU apareció primero en `0.0.0.0`; al asignarle IP desde MAX dejó de reconocerse.
- Después, en MAX: **System State = Safe Mode (User Directed)** y luego **Safe Mode (Improper Installation)**.
- LED STATUS parpadeando **2 veces** = error de software (el sistema operativo no arranca la aplicación).

El problema tenía **cuatro capas**, que hubo que resolver en orden:

| # | Capa | Causa | Solución |
|---|---|---|---|
| 1 | Interruptores DIP | SAFE MODE / NO APP / IP RESET en posiciones de mantenimiento | Dejar todos en OFF salvo USER2 |
| 2 | Línea de arranque de VxWorks | Bootline corrupta en NVRAM: `help.(0,0)[cFP-22x:e2x b=Copyright 2007 ...` | Resetear la bootline por consola serial (`r`) con SAFE MODE en ON |
| 3 | Software del cFP | Instalación incompleta | *Format Disk* + reinstalar FieldPoint 6.0.2 desde MAX |
| 4 | Programa y variables | El formateo borra `startup.rtexe` y las librerías de variables | Restaurar por FTP desde el respaldo y redesplegar `DATOS_PAC` / `pid` |

## 0. Antes de tocar nada: respaldo FTP

El cFP tiene FTP anónimo (`ftp://192.168.114.8`). Copiar **todo** el disco (`/c/ni-rt.ini`, `/c/ni-rt/startup`, `/c/ni-rt/system`, `/c/tmp`) a una carpeta local. El del 21-oct está en `Y:\Downloads\BACKUP_cFP2026-10-21\`.

Diagnóstico de solo lectura: `python herramientas/diag_cfp.py` (genera `DIAG_cFP_<fecha>` con listado y archivos de texto).

## 1. Interruptores DIP (frente del cFP-2200)

| Switch | Posición correcta | Función |
|---|---|---|
| IP RESET | OFF | En ON borra la IP (arranca en 0.0.0.0) |
| SAFE MODE | OFF (ON solo para el paso 2) | En ON arranca sin cargar LabVIEW RT |
| NO APP | OFF | En ON no ejecuta `startup.rtexe` |
| CONS. OUT | OFF | En ON envía la consola de VxWorks por el puerto serial |
| USER1 | OFF | No tocar (definido por usuario) |
| USER2 | **ON** | Estado encontrado; **no tocar** |

Cada cambio de DIP requiere apagar y encender los 24 V.

## 2. Bootline de VxWorks por consola serial

1. Cable serial **null-modem** entre el puerto RS-232 del cFP y la PC del laboratorio (Windows XP).
2. HyperTerminal: *Inicio → Programas → Accesorios → Comunicaciones → HyperTerminal*; COM1, **9600 baudios, 8 bits, sin paridad, 1 bit de parada, sin control de flujo**.
3. Poner **CONS. OUT en ON** y **SAFE MODE en ON**, apagar y encender. Aparece la cuenta regresiva; pulsar una tecla para entrar al prompt `[VxWorks Boot]:`.
4. `p` muestra la bootline actual (estaba corrupta). `?` muestra la ayuda.
5. `r` → **resetea la bootline a los valores de fábrica**. Solo se guarda en NVRAM si SAFE MODE está en ON (en el primer intento, con SAFE MODE en OFF, no se guardó).
   Valores por defecto: dispositivo `tffs=0,0`, archivo `/c/ni-rt/system/vxWorks`, flags `0x8`.
6. `p` para confirmar y `@` para arrancar.
7. Volver SAFE MODE y CONS. OUT a OFF; apagar y encender.

Datos vistos en la consola: bootrom **1.1.0** (30-jul-2007), BIOS 1.1.

## 3. Reinstalar el software (MAX en la PC XP)

1. MAX → *Remote Systems* → `presion` → clic derecho **Format Disk** (borra todo el disco del cFP; por eso el paso 0).
2. *Software* → **Add/Remove Software** → asistente: elegir la versión **FieldPoint 6.0.2** / LabVIEW RT 8.6 (la que tenía, según `ni-rt.ini`) con los componentes: PID Control Toolkit 8.6, Network Variable Engine 1.5, Variable Client Support 1.5, Modbus I/O Server 1.5, DataSocket 4.5.5, NI-VISA 4.4, NI-Serial RT 3.3.2, NI-Watchdog 3.0, Web Server, System State Publisher.
3. *Finish* y esperar el reinicio. Si queda en "Improper Installation" más de 15 min, apagar y encender los 24 V.
4. Resultado esperado en MAX: **System State = Connected – Running**.

## 4. Red

En MAX → *Network Settings*: IP **192.168.114.8**, máscara 255.255.255.0, gateway 192.168.114.1, *Time Server* 192.168.114.80. Nombre `presion`.

## 5. Restaurar el programa

1. Por FTP copiar desde el respaldo a `/c/ni-rt/startup/`: `startup.rtexe` (359 353 bytes) y la carpeta `data\`.
2. Verificar que `ni-rt.ini` tenga `RTTarget.LaunchAppAtBoot=True` y `RTTarget.ApplicationPath=C:\ni-rt\startup\startup.rtexe` (comparar con `BACKUP_cFP2026-10-21\ni-rt.ini`).
3. Reiniciar desde MAX.

## 6. Configuración de E/S (MAX)

Comprobar que coincide con el `.iak` original de 2009:
- `cFP-DI-301 @1`, `cFP-DO-403 @2`, `cFP-AIO-610 @3`.
- AIO-610 entradas 0–3: rango **0 a 0,024 A**.
- AIO-610 salidas 0–3: rango **0 a 10,2 V**, valor de encendido ≈ 0 V, watchdog deshabilitado.

## 7. Redesplegar las variables compartidas

El formateo borra las librerías de variables que hospeda el cFP. En la PC XP con LabVIEW 8.6:

1. Abrir **`MOD_PRESION.lvproj`** (el original, **no** `2026-presion`).
2. Bajo el target `presion (192.168.114.8)` → clic derecho en `DATOS_PAC.lvlib` → **Deploy**; igual con `pid.lvlib`.
3. Verificar en *Distributed System Manager* (DSM): `192.168.114.8` → `DATOS_PAC` y `pid` con valores vivos; `FP` → `3AIO` con las corrientes.

## 8. Verificación final

- MAX: *Connected – Running*; LED STATUS apagado.
- DSM: `DATOS_PAC/TRANS_PRESION` ≈ 0,004 (4 mA en reposo), `SEL_MANUAL` o `SEL_AUTO` según el selector.
- HMI TPC-2106T y SCADA `PRESION.exe` muestran la presión.
- Desde la VM: `python probe_ni_vm3.py` lee las variables (status 2).

## Notas

- **Nunca** aceptar en MAX de la VM o de la laptop "actualizar software" del cFP: cambiaría la versión de LabVIEW RT y el `startup.rtexe` 8.6 dejaría de correr.
- Pendiente físico: dejar CONS. OUT en OFF y retirar el cable null-modem.
