# 01 · Auditoría del sistema de control remoto — nivel-mcn09

*29-oct-2026 · modo actual: DRY-RUN · ninguna dirección verificada · sin escritura real.*

## 1. Alcance de la auditoría

Archivos revisados:

| Área | Archivos |
|---|---|
| Backend | `Program.cs`, `Control/ControlService.cs`, `Control/ControlContrato.cs`, `Control/ControlOpciones.cs`, `Control/ControlMqtt.cs`, `Control/ControlAuth.cs`, `Control/ControlAuditoria.cs` |
| Conectores | `conectores/conector_control_nivel.py`, `conectores/enviar_cmd.py` |
| Frontend | `components/scada/ControlPanel.tsx`, `services/control.ts`, `pages/LevelScadaPage.tsx` |
| Pruebas | `tests/MCP.Industrial.Api.Tests/ControlTests.cs` (25 pruebas) |
| Docs | `docs/control-puesta-en-marcha.md` |

## 2. Matriz de comandos (estado tras la implementación de este ciclo)

| Comando | Rol mínimo | Rango | Dirección candidata | Tipo | Escala | Condición previa | Pulso | Confirmación esperada | Estado |
|---|---|---|---|---|---|---|---|---|---|
| Iniciar | operador | — | `B3:0/4` (candidata) | bit | 1/0 | PLC conectado · selector REMOTO · sin alarma nivel bajo T1 · telemetría fresca ≤30 s | 500 ms (configurable `--pulso-ms`), vuelve a 0 | Bit leído tras el pulso = 0 + (futuro) marcha `O:0/2` observable | NO_VERIFICADA |
| Detener | operador | — | *sin candidata* | — | — | ídem | — | Falta candidata: probablemente diferencial/pulsador físico, no bit PC | PENDIENTE_INSPECCIÓN |
| Reiniciar | operador | — | *sin candidata* | — | — | ídem | — | ídem | PENDIENTE_INSPECCIÓN |
| Setpoint | supervisor | 0–40 cm (unidad `cm` obligatoria) | `N7:5` (candidato) | entero | cuentas = cm (escala por confirmar: ¿raw o cm?) | ídem | — | Relectura `N7:5` = valor escrito | NO_VERIFICADA |
| ParametroPid | supervisor | kp 0–50 · ti 0–600 · td 0–60 | `N7:8/9/10` (candidatos, conjunto A) | entero | sin confirmar | ídem | — | Relectura del registro = valor escrito | NO_VERIFICADA |
| AbrirValvula | supervisor | — | *sin candidata* (la salida es `O:0/4`: PROHIBIDO) | — | — | ídem | — | Secuencia ladder de carrera (T4:0) por confirmar | BLOQUEADO_POR_DISEÑO |
| CerrarValvula | supervisor | — | *sin candidata* (la salida es `O:0/5`: PROHIBIDO) | — | — | ídem | — | Secuencia ladder de carrera (T4:1) por confirmar | BLOQUEADO_POR_DISEÑO |

## 3. Diferencias detectadas y resueltas en este ciclo

| # | Diferencia | Acción |
|---|---|---|
| 1 | El contrato no tenía estados **Validando / Escrito / Confirmado** (solo Aceptado cerraba la orden) | Añadidos al enum `EstadoComando`; Aceptado y Escrito quedan abiertos hasta Confirmado/Timeout |
| 2 | No existía la distinción **Aceptado = recibió · Escrito = escribió · Confirmado = lectura posterior coincide** | `ProcesarAck` procesa los 4 estados; CONFIRMADO con `valor_leido ≠ valor_esperado` → Error `CONFIRMACION_NO_COINCIDE`. La entrega MQTT jamás confirma |
| 3 | No se validaba **unidad** del Setpoint | `UnidadInvalida` si ≠ `cm` (backend y conector) |
| 4 | No se validaba **equipo exacto** `nivel-mcn09` | `EquipoInvalido` (backend y conector) |
| 5 | No se validaba **telemetría fresca** | `TelemetriaVencida` si el último mensaje del edge tiene >30 s (`ControlContrato.TelemetriaMaxSegundos`) |
| 6 | No se validaba **MQTT de nivel** en el preflight | `MqttNoDisponible` |
| 7 | La orden no incluía **correlación, comentario ni origen** | Campos nuevos en `SolicitudComando`/`OrdenControl` y en el payload MQTT |
| 8 | El conector no revalidaba con la telemetría del edge | Se suscribe a `funcional/#`; en real es estricto (TELEMETRIA_VENCIDA/PLC_DESCONECTADO/SELECTOR_NO_REMOTO); en dry-run solo rechaza con evidencia positiva |
| 9 | `docs/control-puesta-en-marcha.md` listaba el ciclo viejo de estados | Actualizado (ver §7) |

## 4. Discrepancias — resueltas con la transcripción del ladder (29-oct-2026)

Fuente: `03_MODULOS-INDUSTRIALES\MCN\07_PLC_RSLOGIX\ladder_control_nivel_micrologix1100.md`
(programa vigente en el PLC, rungs 0000–0023). Ver detalle en `02-mapa-verificacion-rslogix.md`.

| # | Discrepancia anterior | Resolución |
|---|---|---|
| D1 | `B3:0/3` = "selección de mando" vs "panel" | **`B3:0/3` = PC_HMI** (0=PC, 1=HMI, escrito externo) — texto de allowlist corregido en C# y Python |
| D2 | `B3:0/4` "start PC" vs `b3:0/2` "inicio PC" | Ambos existen y son distintos: **`B3:0/4` = START_PC (externo)** y `B3:0/2` = sello INICIO_PC (rung 0005). Candidata de arranque correcta |
| D3 | Escala del setpoint `N7:5` | **Resuelta y crítica:** `N7:5 → PD12:0.SPS` en **cuentas del sensor** (`raw = 16348 − 400·cm`); el contrato en cm debe codificar antes de escribir |
| D4 | Escala Kp/Ti/Td | Destino confirmado (`N7:8..10 → PD12:0.KC/Ti/TD`, rung 0022); unidades en línea (KC=100, Ti/TD=1000) **sin coincidir con N7=0** → pendiente de verificación en laboratorio |
| D5 | `Detener` sin candidata | **Resuelta:** `B3:0/4 ← 0` (sello en serie + watchdog 1.02 s) — CONFIRMADA POR RUNG, pendiente de validación presencial |

Nuevas candidatas detectadas: `B3:0/13` (START_VALVU) y `B3:1/11` (INICIO_SOFTWARE).
**Cambio de semántica detectado:** los bits de arranque son de **NIVEL** (mantener),
no de pulso — el conector distingue `escritura: nivel|pulso` por dirección.

## 5. Cobertura de pruebas (dotnet test → 25/25 ✔)

Cubiertos en C#: autenticación (401), viewer (403), operador con setpoint (403), setpoint válido/​fuera de rango/​unidad incorrecta, equipo inválido, duplicada, vencida, PLC caído, MQTT caído, telemetría vencida, selector LOCAL/REMOTO, nivel bajo T1, allowlist sin O:0/O:1 y 0/13 verificadas, triple gate incompleto, ack aceptado/rechazado/duplicado, timeout (sin ack y tras ESCRITO), lectura posterior coincidente/distinta, flujo completo simulador, trazabilidad (correlación/comentario/origen).

Pertenecen al conector Python (modo real, hoy inalcanzable por 0/13 verificadas) y se ejercitan en la simulación: pulso que vuelve a cero, pérdida de conexión durante el pulso.

## 6. Reglas duras verificadas en código

- El backend **no acepta direcciones** (`SolicitudComando` no tiene ningún campo de dirección).
- `ControlContrato.EsSalidaProhibida` bloquea `O:0*` y `O:1*`; el conector además bloquea `I:*` y `S:*`.
- Las 13 direcciones están con `verificada=false` en **ambos** lados (C# y Python) — test `Allowlist_sin_salidas_prohibidas_y_todas_no_verificadas`.
- El modo REAL exige triple gate (entorno `CONTROL_REAL=1` + config `Modo=Real` y `HabilitadoEscritura=true` + selector REMOTO) y, en el conector, dirección VERIFICADA.
- Auditoría JSONL por evento (ENVIO/ACK/TIMEOUT/VALIDACION/PUBLICACION_FALLIDA) con usuario, rol, orden y motivo.

## 7. Ciclo de vida vigente

```
Recibido → Validando → Enviado → (ack) Aceptado → Escrito → Confirmado
                     ↘ Rechazado · Vencido · Timeout · Error
```

- **Aceptado**: el conector recibió y validó la orden.
- **Escrito**: el conector ejecutó la escritura (solo modo real; hoy inalcanzable).
- **Confirmado**: una lectura posterior coincide con el valor esperado (en dry-run/simulador: proceso completado sin escritura, `escrito=false`).
- **Timeout**: sin confirmación antes de `TimeoutSegundos` (aplica a Enviado/Aceptado/Escrito).

## 8. Confirmación de seguridad

> **No se habilitó control real.** `Control:HabilitadoEscritura=false`, sin `CONTROL_REAL`, 0/13 direcciones verificadas, y ninguna función de escritura es invocable en los modos dry-run/simulador.
