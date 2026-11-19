> **DESCARTADO (21-oct-2026).** Esta alternativa nunca se implementó: se reemplazó por la lectura DataSocket desde la VM Windows 7 (`historiador/conector_edge_cfp2200.py`). Ver `README.md` §3.

# puente_presion.vi — PC XP del laboratorio (LabVIEW 8.6)

Solo LEE variables del cFP-2200 (192.168.114.8) y las envía por UDP a la laptop (192.168.114.77:5055).
No escribe nada en el cFP. No se despliega en el cFP: corre en la PC XP como VI normal ("My Computer").

## 1. Crear el VI
LabVIEW 8.6 → File → New VI (NO dentro de MOD_PRESION.lvproj). Guardar como `C:\puente_presion\puente_presion.vi`.

## 2. Constantes (diagrama de bloques)
Crea 4 arreglos de string constantes:

**NOMBRES_NUM** / **URLS_NUM** (mismo orden)
| Nombre | URL |
|---|---|
| TRANS_PRESION | `psp://192.168.114.8/DATOS_PAC/TRANS_PRESION` |
| POTENCIOMETRO | `psp://192.168.114.8/DATOS_PAC/POTENCIOMETRO` |
| VARIADOR | `psp://192.168.114.8/DATOS_PAC/VARIADOR` |
| VAL_PROPOR | `psp://192.168.114.8/DATOS_PAC/VAL_PROPOR` |
| AI0_A | `psp://192.168.114.8/FP/3AIO/00` |
| AI3_A | `psp://192.168.114.8/FP/3AIO/03` |
| setpoint_pc | `psp://192.168.114.8/pid/setpoint_pc` |
| SETPOINT_TPM | `psp://192.168.114.8/pid/SETPOINT_TPM` |
| salida_pid | `psp://192.168.114.8/pid/salida_pid` |
| valvula_pc | `psp://192.168.114.8/pid/valvula_pc` |
| Kp_PC | `psp://192.168.114.8/pid/Kp_PC` |
| Ti_PC | `psp://192.168.114.8/pid/Ti_PC` |
| Td_PC | `psp://192.168.114.8/pid/Td_PC` |

**NOMBRES_BOOL** / **URLS_BOOL**
SEL_AUTO, SEL_MANUAL, ARRANQUE_MANUAL, PARADA_MANUAL, PRESOS, SWITCH_NB, SWITCH_NA,
LED_SIST_FUN, ACT_VARIADOR, LED_NA, LED_NB → `psp://192.168.114.8/DATOS_PAC/<NOMBRE>`

> Si `psp://.../FP/3AIO/00` da error, prueba `fieldpoint://192.168.114.8/FP/3AIO/00`.

## 3. Antes del bucle (se ejecuta una vez)
1. **For Loop** sobre URLS_NUM → dentro **DataSocket Open** (Data Communication › DataSocket), mode = **Read**.
   Sale un arreglo de refnums `REF_NUM`. Igual para URLS_BOOL → `REF_BOOL`.
2. **UDP Open** (Data Communication › Protocols › UDP), port = 0 → `conexion`.
3. **String To IP** con `"192.168.114.77"` → `ip_laptop`.

## 4. While Loop (cada 1 s)
1. **Wait (ms)** = 1000. Botón **stop** en el panel → condición de parada.
2. **For Loop** auto-indexando `REF_NUM` y `NOMBRES_NUM`:
   - **DataSocket Read** (refnum, type = constante **DBL**, timeout = 500 ms).
   - Unbundle del error → `status`. **Select**: si status=TRUE usar NaN, si no el valor.
   - **Format Into String** formato `%s=%.4f` (nombre, valor) → un string por elemento.
   - No encadenes el error al siguiente ciclo; cada lectura es independiente.
3. **For Loop** igual con `REF_BOOL` / `NOMBRES_BOOL`: type = constante **Boolean**, luego
   **Boolean To (0,1)** y **Format Into String** `%s=%d` (si error → `%s=NaN`).
4. **Build Array** (concatenate) de ambos arreglos → **Array To Spreadsheet String**
   con delimitador `;` y formato `%s`.
5. **UDP Write**: conexion, address = `ip_laptop`, port = **5055**, data = el string.

## 5. Después del bucle
**DataSocket Close** de cada refnum (For Loop) y **UDP Close**. Run (flecha) y dejarlo corriendo.

## 6. En la laptop
```
cd Y:\proyects26\tesis\historiador
python conector_edge_cfp2200.py
```
Permitir **UDP 5055 entrante** en el Firewall de Windows (python.exe). Deben aparecer líneas
`presion/pv = ...`, `estado/selector_manual = True`, etc. bajo
`uss/campus/lab-automatizacion/sl01la07/presion-mcp09/funcional/...`.

## Reglas
- NO usar DataSocket Write, Shared Variable en modo write, ni "Set" en DSM.
- NO abrir ni desplegar nada de MOD_PRESION.lvproj desde este VI.
