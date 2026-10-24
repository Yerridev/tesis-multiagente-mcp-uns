# Módulo de control de temperatura MCT-09/001 — Schneider Twido

Cuarto equipo integrado a la arquitectura de la tesis. Módulo didáctico de **Inducontrol Ingeniería S.A.C.** (manual de 2007/2009) del Laboratorio de Automatización y Simulación de Procesos de la USS.

> **Regla del proyecto:** integración **solo lectura**. El conector `historiador/conector_edge_twido.py` no tiene funciones de escritura. El script de diagnóstico `diag_twido.py` sí puede escribir (arranque y parada de prueba), pero solo con confirmación explícita y autorización del responsable.

*Actualizado: 23-oct-2026 — puesta en marcha, recuperación de HMI/SCADA e integración completa.*

## 1. Equipo y proceso

```text
   ┌──────────────┐  T1 superior (enfriamiento, 125 L): serpentín + enfriador (relé R_02), Pt100 "enfriador"
   │      T1      │  interruptores de nivel alto/bajo
   └──────┬───────┘
          │ descarga por gravedad (V2)
   ┌──────┴───────┐  T2 inferior (principal, 125 L): RESISTENCIA (PWM por relé de estado sólido), Pt100 "principal" (PV)
   │      T2      │  interruptores de nivel alto/bajo
   └──────┬───────┘
          ▼ bomba Pentax Ultra U5 + Altivar 11 (recircula T2 → T1; perturbación por velocidad)
```

| Elemento | Detalle |
|---|---|
| PLC | **Twido TWDLCAE40DRF** + 2× **TWDAMM3HT** (2 entradas 4–20 mA + 1 salida 0–10 V, 12 bits) |
| Comunicación | Modbus TCP 502, unit id 1, IP `192.168.114.10` (fija en el PLC) |
| Sensores | 2× Danfoss MBT 5252 Pt100 + transmisor 4–20 mA; 4× Kobold NKP |
| Actuadores | Resistencia por PWM (FOTEK SSR-25DA-H, **sin disipador**); Altivar 11 ATV11HU29M3A; enfriador |
| Tablero | Pilotos SISTEMA ENERGIZADO / FUNCIONANDO / RESISTENCIA FUNCIONANDO, 4 alarmas de nivel, pulsadores HABILITAR/DESHABILITAR ENFRIADOR, selector CONTROLADOR HMI–0–PC, paro de emergencia |
| Rango de operación | 15–50 °C (fabricante) |

## 2. Cómo funciona el arranque (programa del PLC)

El lazo arranca solo si se cumplen **las tres** condiciones:

1. Selector en **PC** (`%M0`) o **HMI** (`%M1`).
2. **Sin falla de nivel** (`%M20 = %M21 = 0`): el agua entre el nivel bajo y el alto en **ambos** tanques.
3. **Flanco 0→1** en `%M30` (PC) o `%M32` (HMI), que debe **mantenerse en 1**.

Entonces corre el PID 0 (PV `%IW0.2.0`, SP `%MW100`, Kp/Ti/Td `%MW101–103`, salida `%MW110` → PWM `%Q0.0.1`), se encienden SISTEMA FUNCIONANDO (`%M12`) y la bomba (`%M13` → LI1). **SP y parámetros se pierden al apagar el PLC**: los carga el SCADA o la HMI.

## 3. Cadena HMI / SCADA (recuperada el 23-oct-2026)

```text
HMI TPC-2106T (.101) ── variables compartidas LIB_HMI/LIB_PC ──► PC XP (.100)
                                                                   │ MOD_TEMP.exe (scada_mct_04.vi)
                                                                   │ DataSocket opc://localhost/National Instruments.OPCLookoutDrivers/temp.N
                                                                   ▼
                                       Industrial Automation OPC Servers 5.1, objeto Modbus "temp"
                                                                   │ Modbus TCP
                                                                   ▼
                                                            Twido (.10)
```

- La HMI **no habla con el PLC**: depende de que `MOD_TEMP.exe` esté abierto en la PC `.100`.
- Ítems OPC: `temp.N` = bobina `%M(N−1)`; `temp.4000N` = `%MW(N−1)`.
- **PollRate del objeto `temp` = `0:01`.** Lookout mide el tiempo en **días**: con `1.0` lee una vez al día y el SCADA se queda congelado.
- El proyecto `MCT.lvproj` tiene desactivado el auto-despliegue: hay que desplegar `LIB_PC.lvlib` y `LIB_HMI.lvlib` desde LabVIEW 8.6.
- OPC Server instalado sin número de serie (modo evaluación).

## 4. Escalas (las del SCADA original)

| Magnitud | Fórmula |
|---|---|
| Temperatura y setpoint | `°C = cuentas × 100 / 4095` (el SP va en las **mismas cuentas**, no en la escala 0–10000 del bloque PID) |
| Velocidad de la bomba | `% = %MW10 / 40,96` (100 % = 10 V = 50 Hz con `AIt = 10U`) |
| Salida del PID | `% = %MW110 / 100` |

La señal tiene **ruido de ±1 °C** con la bomba en marcha; el conector publica media móvil de 10 s en los topics en °C.

## 5. Variables

Mapa completo con estado *confirmado/hipótesis*: [`tags_temperatura.yaml`](tags_temperatura.yaml) (39 tags). UNS: `uss/campus/lab-automatizacion/sl01la07/temperatura-mct09/funcional/...`; en la base, prefijo `temperatura-mct09/`.

## 6. Hallazgos y correcciones del 23-oct-2026

| # | Hallazgo | Acción |
|---|---|---|
| 1 | SP, Kp, Ti, Td en 0 tras el encendido | Se cargan desde SCADA/HMI (o `diag_twido.py --arrancar-pc` en pruebas) |
| 2 | Altivar 11 gama Asia en **mando local** de fábrica (`rdY`, solo RUN del teclado) | `FUn → tCC → ACt = 2C` y `FUn → LSr = tEr` (ENT 2 s en ambos) y `AIt = 10U`; sin `LSr` la velocidad seguía saliendo de la perilla frontal |
| 3 | SCADA sin datos: faltaba el OPC Server | Instalación + objeto `temp` + PollRate `0:01` + despliegue de variables |
| 4 | Escala del SP mal supuesta (3000 = 73 °C) | Corregida en `diag_twido.py` con el diagrama del SCADA |
| 5 | **Calentamiento con el lazo detenido y olor a quemado**: relé de estado sólido FOTEK sin disipador | ⚠️ Pendiente: revisar/reemplazar con disipador. El MCP lo detecta como `CALENTAMIENTO_SIN_ORDEN` |
| 6 | El respaldo `Twido1.xtwd` (2009) no tiene `%M41/%M42`, que sí usa el SCADA | No descargar el respaldo; subir el programa real con TwidoSuite |
| 7 | El Twido usa `.10`, la IP que tenía la laptop (y que exige el enlace 1 del S7-200) | Laptop a `.12`; caudal pendiente (ver `red_laboratorio_plc.md`) |

## 7. Archivos

| Archivo | Uso |
|---|---|
| `tags_temperatura.yaml` | Diccionario de variables |
| `diag_twido.py` | Diagnóstico Modbus (`--loop`, solo lectura); `--arrancar-pc` / `--detener-pc` escriben con confirmación |
| `../historiador/conector_edge_twido.py` | Conector edge → MQTT (solo lectura) |
| `../historiador/db/07_temperatura_v01.sql` | Rango 15–50 °C del fabricante |
| `../historiador/grafana/dashboards/temperatura_mct09.json` | Dashboard |
| `../historiador/mcp_servidor/servidor_mcp_temperatura.py` | Servidor MCP con `diagnosticar_temperatura` |
| `../historiador/mcp_servidor/conocimiento/grafo_mct09.json` | Knowledge graph |
| Históricos | `importar_lvm.py <carpeta historico> --modulo temperatura` (13 archivos 2009–2011) |

## 8. Pendientes

1. Relé de estado sólido: revisión/reemplazo con disipador; repetir la medición de calentamiento.
2. Contrastar la escala con termómetro.
3. Respaldar el programa real del Twido (subir, **no** descargar).
4. Licencia del OPC Server o alternativa.
5. Casos de evaluación de temperatura en `evaluacion/reproducir_casos.py`.
