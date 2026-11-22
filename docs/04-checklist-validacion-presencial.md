# 04 · Checklist de validación presencial en laboratorio (nivel-mcn09)

*Este checklist SOLO se ejecuta con personas presentes, equipo detenido y respaldo del RSS.
Ningún paso habilita escritura real por sí solo: cada comando se aprueba antes de pasar al
siguiente. Fecha de la campaña: ____/____/2026 · Responsable(s): ______________*

## A. Preparación (antes de tocar el software)

| # | Ítem | ✔ |
|---|---|---|
| 1 | Responsables presentes identificados (operador + supervisor) | ☐ |
| 2 | Copia del RSS verificada (`upload final.RSS` + backup reciente, checksum anotado) | ☐ |
| 3 | Equipo MCN-09 detenido (sin arranque automático) | ☐ |
| 4 | Bomba Pentax desenergizada inicialmente (guardamotor abierto) | ☐ |
| 5 | Nivel de agua seguro en T1/T2 (< 20 cm) | ☐ |
| 6 | Paro físico (pulsador STOP / diferencial) probado y accesible | ☐ |
| 7 | Selector de mando físicamente en **LOCAL** | ☐ |
| 8 | RSLogix 500 en línea, monitorizando `N7:5`, `B3:0`, `T4:0/1`, `O:0/2` | ☐ |
| 9 | Backend en DRY-RUN (`Control:HabilitadoEscritura=false`, sin `CONTROL_REAL`) | ☐ |
| 10 | Conector de control en `--modo dry-run` y respondiendo acks | ☐ |

## B. Ficha del comando bajo prueba (una fila por comando, en orden)

| Campo | Registro |
|---|---|
| 9. Comando que se probará | _______________ |
| 10. Dirección candidata | _______________ |
| 11. Valor anterior (leído en RSLogix) | _______________ |
| 12. Valor solicitado | _______________ |
| 13. Valor posterior (leído en RSLogix) | _______________ |
| 14. Resultado (OK / NO_OK / NO_APLICABLE) | _______________ |
| 15. Evidencia (captura RSLogix / auditoría JSONL / foto) | _______________ |
| 16. Procedimiento de reversión aplicado | _______________ |

## C. Orden de validación (no avanzar sin aprobar el anterior)

| Paso | Comando | Criterio de aprobación |
|---|---|---|
| 1 | Lectura de registros | MQTT muestra los mismos valores que el monitor de RSLogix |
| 2 | Escritura sobre registro interno inocuo (p. ej. `N7:2` tiempo de cierre con válvula detenida) | Valor cambia en RSLogix y vuelve al original al revertir |
| 3 | Setpoint con equipo detenido | `N7:5` cambia al valor pedido (0–40); sin movimiento de bomba |
| 4 | Setpoint con confirmación visual en RSLogix | El PD12:0 usa el nuevo SP (se observa la consigna interna) |
| 5 | Pulso interno sin energizar bomba | Bit `B3:0/4` (si se confirma) va a 1 y **vuelve a 0** en <1 s |
| 6 | Arranque con condiciones seguras (nivel T1 OK, LOCAL supervisado) | `O:0/2` enciende la luz de marcha; parada inmediata verificada |
| 7 | Parada | `O:0/2` se apaga; bomba responde al paro |
| 8 | Parámetros PID (Kp/Ti/Td) | Registros N7:8..10 cambian en la escala confirmada; el PD12 responde |
| 9 | Válvula (solo si la carrilera lo permite sin escribir O:0/*) | Carrera T4:0/T4:1 completa sin forzar salidas |

**Regla**: no habilitar el siguiente comando hasta aprobar el anterior. Marcar
`verificada=true` en `ControlContrato.cs` y `conector_control_nivel.py` SOLO después del
paso 15 con evidencia.

## D. Al cerrar la campaña

| # | Ítem | ✔ |
|---|---|---|
| 1 | Selector de vuelta a LOCAL | ☐ |
| 2 | `CONTROL_REAL` sin definir y `HabilitadoEscritura=false` | ☐ |
| 3 | Conector de control detenido | ☐ |
| 4 | Auditoría JSONL exportada y respaldada | ☐ |
| 5 | Fichas de la tabla B archivadas con las evidencias | ☐ |
| 6 | `docs/02-mapa-verificacion-rslogix.md` actualizado con direcciones verificadas | ☐ |
