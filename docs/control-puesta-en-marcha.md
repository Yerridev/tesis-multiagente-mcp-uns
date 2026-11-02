# Control remoto de nivel-mcn09 — puesta en marcha (DRY-RUN)

Infraestructura de control **sin escrituras al PLC**. El backend nunca escribe: solo valida,
audita y publica la orden en MQTT; quien podría escribir (en el futuro) es el conector Python,
tras su propio triple gate y solo con direcciones **VERIFICADAS**.

```
SPA #/mod-nivel ──HTTPS/JSON (Bearer)──► ASP.NET /api/control/*  (valida + audita)
                                            │ SignalR  «controlResultado»
                                            │ MQTT    {base}/control/cmd   → conector Python
                                            ◄── MQTT  {base}/control/ack   (ACEPTADO/RECHAZADO)
                                            ◄── MQTT  {base}/control/state (modo, simulador)
```

Base de tópicos: `uss/campus/lab-automatizacion/sl01la07/nivel-mcn09/control`

## 1. Contrato de comandos (resumen)

| Tipo | Valor | Rango | Rol mínimo |
|---|---|---|---|
| Iniciar | — | — | operador |
| Detener | — | — | operador |
| Reiniciar | — | — | operador |
| Setpoint | cm | 0–40 | supervisor |
| ParametroPid | kp / ti / td | kp 0–50 · ti 0–600 · td 0–60 | supervisor |
| AbrirValvula | — | — | supervisor |
| CerrarValvula | — | — | supervisor |

**Estados:** Recibido → Validando → Enviado → Aceptado → Escrito → Confirmado
| Rechazado | Vencido | Timeout | Error.
**Confirmación:** `CONFIRMADO` exige una lectura posterior que coincida con el valor
esperado (en dry-run/simulador: proceso completado sin escritura). La entrega MQTT nunca
confirma. Ver `01-auditoria-control-remoto.md` §7.
**Motivos:** `RANGO_INVALIDO`, `PERMISO_INSUFICIENTE`, `SIN_AUTENTICACION`, `PLC_DESCONECTADO`,
`SELECTOR_NO_REMOTO`, `NIVEL_BAJO_T1`, `DUPLICADA`, `VENCIDA`, `SIN_CONFIRMACION`,
`MQTT_NO_DISPONIBLE`, `DIRECCION_PROHIBIDA`, `NO_VERIFICADAS`, `REAL_NO_ARMADO`,
`EQUIPO_INVALIDO`, `UNIDAD_INVALIDA`, `TELEMETRIA_VENCIDA`, `CONFIRMACION_NO_COINCIDE`.

**Reglas duras:**
- Jamás se escriben salidas `O:0/*`, `O:1/*`, ni entradas `I:*`/`S:*` (guard en backend y conector).
- Preflight (ambos modos): MQTT disponible + telemetría fresca (≤30 s) + PLC conectado +
  selector REMOTO; `Iniciar` additionally exige sin alarma de nivel bajo de T1.
- Setpoint exige unidad `cm`; el equipo debe ser exactamente `nivel-mcn09`.
- El conector revalida con su propia suscripción a `funcional/#` (PLC, selector, frescura).

## 2. Triple gate del modo REAL

La escritura real solo queda armada si se cumplen **simultáneamente**:

1. Variable de entorno `CONTROL_REAL=1`.
2. Configuración `Control:Modo=Real` **y** `Control:HabilitadoEscritura=true` (`appsettings.json`).
3. Selector físico en **REMOTO** (lectura real de `estado/selector_remoto`, y en el conector `I:0/0`).
4. Además, en el conector: dirección con `verificada=true` en la allowlist y **NO** prohibida (O:0/O:1).

Si falta cualquiera, el modo efectivo es **DRY-RUN** (visible en la píldora de la UI).

## 3. Allowlist de direcciones candidatas (TODAS NO_VERIFICADAS)

| Tag | Dirección | Uso candidato | Estado |
|---|---|---|---|
| B3:0/3 | B3:0/3 | Selección de mando | NO_VERIFICADAS |
| B3:0/4 | B3:0/4 | Arranque desde PC | NO_VERIFICADAS |
| B3:0/5 | B3:0/5 | Arranque desde HMI | NO_VERIFICADAS |
| N7:5 | N7:5 | Setpoint 1 | NO_VERIFICADAS |
| N7:6 | N7:6 | Setpoint 2 | NO_VERIFICADAS |
| N7:8..10 | N7:8, N7:9, N7:10 | Kp/Ti/Td modo A | NO_VERIFICADAS |
| N7:11..13 | N7:11, N7:12, N7:13 | Kp/Ti/Td modo B | NO_VERIFICADAS |
| N7:1 | N7:1 | Tiempo apertura válvula | NO_VERIFICADAS |
| N7:2 | N7:2 | Tiempo cierre válvula | NO_VERIFICADAS |

La misma lista vive en `backend/Control/ControlContrato.cs` y en
`conectores/conector_control_nivel.py`. **Confirmar cada dirección en RSLogix antes de marcarla
VERIFICADA** (cambiar `verificada: false → true` en ambos archivos) y solo entonces probar real.

## 4. Cómo se ejecuta hoy (dry-run)

```powershell
# backend (sirve también el frontend en http://127.0.0.1:5050)
cd backend
dotnet run --no-launch-profile --urls http://127.0.0.1:5050

# conector de control (opcional; sin él las órdenes quedan en TIMEOUT tras 10 s)
..\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe `
    ..\conectores\conector_control_nivel.py --modo dry-run

# herramienta de laboratorio: enviar una orden y esperar el ack
..\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe `
    ..\conectores\enviar_cmd.py --tipo Iniciar
```

Modos del conector: `dry-run` (por defecto; doble validación con la telemetría del edge y
cierre `CONFIRMADO` sin escritura) · `simulador` (imita al PLC, se identifica como
SIMULADOR en `state`/logs; sirve para probar el flujo completo sin fingir telemetría real) ·
`real` (triple gate + direcciones verificadas; hoy rechaza siempre: 0/13 verificadas;
incluye pulso de bits con `--pulso-ms` y relectura de confirmación).

## 5. Autenticación (desarrollo)

`Authorization: Bearer <clave>` con claves de `appsettings.json → Control:Usuarios`:

| Clave | Rol | Puede |
|---|---|---|
| dev-viewer | viewer | leer estado/órdenes |
| dev-operador | operador | Iniciar/Detener/Reiniciar |
| dev-supervisor | supervisor | todo + auditoría |
| dev-admin | admin | todo |

En producción sustituir por identidad real (OIDC/JWT) conservando la matriz de roles.

## 6. Auditoría

Cada intento queda en `backend/auditoria/control-YYYYMMDD.jsonl` (usuario, rol, orden, estado,
motivo, detalle) y en `GET /api/control/auditoria` (solo supervisor+).

## 7. Pruebas automatizadas

```powershell
cd tests\MCP.Industrial.Api.Tests
dotnet test
```

Cubren (25 pruebas, `dotnet test` en verde): usuario inexistente · viewer sin permiso ·
operador con setpoint · setpoint válido/fuera de rango/unidad incorrecta · equipo inválido ·
duplicada · vencida · PLC desconectado · MQTT desconectado · telemetría vencida ·
selector LOCAL/REMOTO · nivel bajo de T1 · allowlist sin O:0/O:1 y todas NO_VERIFICADAS ·
triple gate REAL · ack aceptado/rechazado/duplicado · timeout (sin ack y tras ESCRITO) ·
lectura posterior coincidente/distinta · flujo completo hasta CONFIRMADO con simulador ·
trazabilidad (correlación/comentario/origen). Casos de pulso/pérdida de conexión en
`01-auditoria-control-remoto.md` §5.

## 8. Checklist de laboratorio (presencial, equipo detenido)

1. RSLogix abierto con el programa vigente del MCN-09; anotar las rutas de: arranque PC,
   setpoint, Kp/Ti/Td, apertura/cierre de válvula.
2. Comparar una a una con la allowlist y marcar `verificada=true` SOLO en las confirmadas.
3. Selector en LOCAL → cualquier orden debe rechazarse con `SELECTOR_NO_REMOTO`.
4. Sin alimentación/PLC apagado → órdenes deben rechazarse con `PLC_DESCONECTADO`.
5. Probar con el equipo **sin agua y bomba desenergizada**.

## 9. Procedimiento de prueba comando por comando (una orden cada vez)

Para cada tipo (empezar por Setpoint):

1. Verificar en RSLogix el valor actual del destino.
2. Enviar la orden en DRY-RUN → comprobar ACEPTADO y `escrito=false` en el ack.
3. Habilitar modo real (triple gate) → enviar → verificar en RSLogix el cambio de valor (online/analog monitor).
4. Probar el caso límite (arriba del rango) → RECHAZADO.
5. Anotar resultado en la auditoría (quién, cuándo, qué).

## 10. Plan de retorno a modo manual

1. Selector físico a **LOCAL** (el PLC ignora el SCADA).
2. `Control:HabilitadoEscritura=false` + quitar `CONTROL_REAL` → el backend queda DRY-RUN aunque alguien lo reinicie.
3. Detener el conector de control.
4. Verificar en el panel físico que bomba/valvula responden solo al mando local.

## 11. Qué queda pendiente SOLO para el laboratorio

- Confirmar direcciones candidatas contra RSLogix (marcar VERIFICADAS).
- Habilitar la escritura real (triple gate) y validar comando por comando con el equipo detenido.
- Nada de esto afecta al modo actual: todo funciona en DRY-RUN hoy.
