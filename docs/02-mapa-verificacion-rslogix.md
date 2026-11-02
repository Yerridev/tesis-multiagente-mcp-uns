# 02 · Mapa de verificación de direcciones de control (MCN-09/001)

> **Evidencia principal (nueva):** transcripción del programa vigente en el PLC →
> `03_MODULOS-INDUSTRIALES\MCN\07_PLC_RSLOGIX\ladder_control_nivel_micrologix1100.md`
> (rungs 0000–0023, añadida el 29-oct-2026). Fuentes complementarias:
> `00_LEEME_INDICE.txt` (mapa E/S), `01_MAPA_ES\…xls`, `04_SCADA_LABVIEW` (shared
> variables), lecturas en vivo por EtherNet/IP y telemetría MQTT (29-oct-2026).
>
> **Regla**: "VERIFICADA" exige además observación en laboratorio (valor anterior /
> solicitado / posterior en RSLogix online). Hoy sigue siendo **0/13 VERIFICADAS**;
> lo que cambia es que muchas candidatas pasan de *hipótesis* a
> **CONFIRMADAS POR RUNG** (evidencia documental del programa).

## 1. LECTURAS ya confirmadas (MQTT ↔ PLC coincidente)

| Dirección | Dato UNS | Valor observado | Evidencia |
|---|---|---|---|
| `N7:4` | `nivel/raw`, `nivel/cm` | ≈16520 cuentas ≈ −0.4 cm | Coincidencia físico→PLC→MQTT; fórmula `(16348−N7:4)/400`; rung 0013 `MOV I:1.1→N7:4` |
| `T4:0.ACC`, `T4:1.ACC` | `valvula/t_apertura`, `t_cierre` | 0 s | rungs 0016/0017 |
| `B3:0` (bits) | marcha/estados | B3:0=257 | rungs 0002–0010 |
| `I:0/0`, `I:0/1` | selector remoto/local | selector en REMOTO (anteayer LOCAL) | rungs 0005/0015 |
| `O:0/0..5`, `O:1.0`, `I:1.0..1` | estados/variador/potenciómetro | según proceso | solo LECTURA |
| `N7:5,6,8..13` | setpoints y PID (catálogo edge) | 0 (PC aún no escribe) | rung 0022 (destino confirmado) |

## 2. Tabla de candidatas a ESCRITURA (actualizada con evidencia de rung)

| Función | Dirección candidata | Evidencia | Escala / codificación | Escritura | Confirmación | Estado |
|---|---|---|---|---|---|---|
| Iniciar (PC) | `B3:0/4` START_PC | **Rung 0005/0006** (XIC START_PC en serie con sello INICIO_PC; flankado por OSR→B3:0/14); "externo" en el mapa de tags | bit; **de NIVEL (mantener en 1)** — §6 del ladder: si se suelta START, cae el sello | `1` sostenido | `O:0/2` SIST_FUNCIONANDO encendido + `B3:0/2` INICIO_PC=1 | CONFIRMADA POR RUNG · pendiente validación en lab |
| Detener (PC) | `B3:0/4` → `0` | **Rung 0005** (sello en serie con START_PC) + rungs 0009/0010 (watchdog T4:4 1.02 s → START_REMOTO cae) | bit en 0 | `0` | `O:0/2` se apaga; `B3:0/2`=0 | CONFIRMADA POR RUNG · pendiente validación en lab |
| Setpoint (PC) | `N7:5` | **Rung 0022**: `MOV N7:5 → PD12:0.SPS` (rama PC, PC_HMI=0) | **ENTERO EN CUENTAS del sensor, NO cm**: raw = 16348 − 400·cm (invertido); evidencia: SPS en línea 12269 ≈ 10.2 cm | entero 0…16348 | relectura `N7:5` + `PD12:0.SPS` | CONFIRMADA POR RUNG · **escala corregida** |
| Setpoint (HMI) | `N7:6` | Rung 0022 rama HMI (`→ SPS` cuando PC_HMI=1) | ídem (cuentas) | entero | relectura | CONFIRMADA POR RUNG |
| Kp/Ti/Td (PC) | `N7:8/9/10` | **Rung 0022**: `MOV → PD12:0.KC/Ti/TD` | unidades del PID MicroLogix (Ti/TD en s o min según configuración; pendiente de confirmar con los valores en línea KC=100 Ti=1000 TD=1000) | enteros 0–50 / 0–600 / 0–60 (rangos de contrato a revisar con la escala real) | relectura `N7:x` y del PD12 | CONFIRMADAS POR RUNG · escala pendiente |
| Kp/Ti/Td (HMI) | `N7:11/12/13` | Rung 0022 rama HMI | ídem | enteros | relectura | CONFIRMADAS POR RUNG |
| Tiempo apertura válvula | `N7:1` | **Rung 0019**: `MOV N7:1 → T4:0.PRE` | **centésimas de segundo** (base 0.01 s): 3500 = 35 s | entero (p. ej. 0–6000) | relectura + `T4:0.PRE`/`T4:0.ACC` | CONFIRMADA POR RUNG · pendiente lab |
| Tiempo cierre válvula | `N7:2` | Rung 0019: `MOV N7:2 → T4:1.PRE` | centésimas de segundo | entero | relectura + `T4:1.PRE` | CONFIRMADA POR RUNG |
| Fuente PC/HMI | `B3:0/3` PC_HMI | Rungs 0005/0007/0014/0022; "externo" | bit: 0=PC, 1=HMI | nivel | cambio de rama visible en rung 0022 | CONFIRMADA POR RUNG · candidata a control de modo (uso correctar en allowlist) |
| Arranque válvula | `B3:0/13` START_VALVU | Rungs 0016/0017; "externo" | bit (¿nivel/pulso?) | pendiente | ABRIENDO/CERRANDO | NUEVA CANDIDATA · pendiente inspección |
| Inicio software | `B3:1/11` INICIO_SOFTWARE | Rungs 0011/0018; "externo" | bit | pendiente | POSICION INICIAL / T4:2 | NUEVA CANDIDATA |
| Reiniciar | *ninguna* | El ladder no tiene reinicio por PC | — | — | — | SIN CANDIDATA (reinicio = ciclo de potencia) |
| Abrir/Cerrar válvula directo | prohibido (`O:0/4`,`O:0/5`) | Rungs 0016/0017: ABRIENDO/CERRANDO son salidas con sello+timer | — | — | — | BLOQUEADO_POR_DISEÑO (usar START_VALVU si se verifica) |

## 3. Correcciones que introduce el ladder a lo anterior

1. **Escala del setpoint (crítico):** el contrato de software asumía `Setpoint en cm 0–40`
   escrito directo a `N7:5`. El ladder muestra que `SPS` vive en **cuentas del sensor**
   con escala invertida. **Antes de cualquier escritura real hay que codificar
   `N7:5 = round(16348 − 400·cm)`** (o cambiar la convención) y verificar con termómetro.
2. **`B3:0/3` no es "selección de mando"**: es `PC_HMI` (elegir fuente PC/HMI).
   Texto de la allowlist corregido en `ControlContrato.cs` y en el conector.
3. **Nivel vs pulso:** los bits de arranque (`B3:0/4`) deben **mantenerse**; un pulso
   de 500 ms volvería a cero y, con el watchdog de 1.02 s, apagaría el lazo.
   La función `escribir_direccion_verificada` distingue ahora `escritura: nivel|pulso`
   por dirección (por defecto pulso; `B3:0/4` documentado como NIVEL). Hoy inalcanzable
   (0/13 verificadas).
4. **Detener por PC = soltar START_PC (B3:0/4 ← 0)**: el sello del rung 0005 va en
   serie con START_PC (confirmado en §6 del ladder). Candidata promovida de "sin
   candidata" a CONFIRMADA POR RUNG.
5. **Discrepancias previas D1/D2 resueltas:** `b3:0/3` = PC_HMI (no "panel");
   `B3:0/2` = sello INICIO_PC (rung 0005) y `B3:0/4` = START_PC externo — el LEEME
   ("start PC") y el contrato coinciden para el arranque.
6. **Nuevos riesgos del ladder** (para el checklist): sin enclavamiento ABRIENDO/CERRANDO;
   O:1.0 conserva valor sin modo; si LOCAL y REMOTO activos gana 0015; rangos 26000 vs
   4914 del PID ×2; los PD12 en línea (KC=100…) no provienen de N7 → verificar rung 0022
   en laboratorio antes de escribir parámetros PID.

## 4. Pendiente de inspección presencial (sigue siendo)

- Confirmar en RSLogix online que `B3:0/4` responde como NIVEL con el equipo detenido
  (ficha del checklist, paso 5–7).
- Escalas reales del PID (KC/Ti/TD) y del setpoint con el sensor contrastado.
- `upload final.RSS` binario: la transcripción .md lo representa; conservar ambos con
  checksum en la campaña de respaldo.

## 5. Proceso para pasar una dirección a VERIFICADA

1. Ficha del checklist con equipo detenido, bomba desenergizada, selector LOCAL.
2. RSLogix online + la transcripción .md como mapa.
3. Escritura de prueba en registro inocuo (p. ej. `N7:2` tiempo de cierre) con
   observación antes/después y reversión.
4. Solo entonces: `verificada: false → true` en **ambos**
   (`ControlContrato.cs` y `conector_control_nivel.py`), con fecha y responsable.
5. Nunca en bloque. **Hoy: 0/13.**
