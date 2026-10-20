# Estado actual del proyecto de tesis

*Actualizado: 19-oct-2026*

## Tema

**Implementación de una arquitectura multiagente basada en inteligencia artificial para la orquestación e integración de datos industriales utilizando Model Context Protocol (MCP).**

## Objetivo general

Implementar una arquitectura multiagente basada en IA y MCP para facilitar la integración, consulta y análisis de datos industriales.

## Arquitectura y avance por capa

```text
PLC S7-200 CPU226 + CP243-1 (Módulo de caudal MCC-09)          ✅ acceso solo lectura por Ethernet (enlace 1)
          │  python-snap7
          ▼
conector_edge_s7200.py v3.2                                     ✅ 21 variables, calidad por modo de operación
          │  MQTT (Mosquitto)
          ▼
UNS  uss/campus/lab-automatizacion/sl01la07/caudal-mcc09/...    ✅ ISA-95; funcional/ + descriptivo/
          │
          ▼
Historiador: ingestor + TimescaleDB + Grafana                   ✅ + históricos .lvm 2008-2011 importados
          │  rol mcp_lector (solo SELECT)
          ▼
servidor_mcp.py v1.0 (7 herramientas)                           ✅ construido y probado con datos simulados
          │                                                     ⏳ falta probarlo con datos reales del laboratorio
          ▼
Agente de consulta → agentes de análisis/diagnóstico + coordinador   ⏳ siguiente fase
          ▼
Knowledge graph del módulo + evaluación experimental                 ⏳ pendiente
```

## Mapa de variables confirmado

Fuentes: proyecto de PC Access `OPC_caudal.pca` (Inducontrol), análisis del programa `ANALISIS_CPU226.awl`, tabla del lazo PID en VB159 y calibración del caudalímetro (`calibracion_caudalimetro.xls`, 13 puntos, R² = 0.9997).

| Variable UNS | Dirección | Unidad | Nota |
|---|---|---|---|
| `caudal/pv_pid` | VD159 | L/min | PV normalizada del PID × 140 |
| `caudal/caudalimetro` | MW3 (copia de AIW0) | L/min | `Q = 0.005498·AIW0 − 34.896`; válido solo en REMOTO |
| `caudal/setpoint_pid` · `caudal/setpoint` · `caudal/setpoint_hmi` | VD163 · VD400 · VD408 | L/min | Setpoint efectivo, desde PC y desde HMI |
| `actuadores/variador_pct` | VW8 (→ AQW2) | % | Salida PID en REMOTO, potenciómetro en LOCAL |
| `actuadores/valvula_pct` | MW25 (→ AQW0) | % | 100 % en LOCAL |
| `actuadores/potenciometro` | MW2 (copia de AIW2) | cuentas | Válido solo en LOCAL |
| `pid/salida`, `pid/kc`, `pid/ti`, `pid/td`, `pid/ts`, `pid/mx` | VD167…VD187 | %, –, min, min, s, – | Tabla del lazo PID |
| `estado/*` | I0.0, I0.1, Q0.0–Q0.2, M0.2, M0.3 | bool | Modo, mando, bomba, niveles |

Hallazgos del 19-oct: Ti/Td estaban etiquetados como Ki/Kd; MW2 y MW3 comparten el byte MB3, lo que convierte a MW3 en una segunda medida del caudal (en REMOTO) y hace inválido a MW2 en ese modo.

## Servidor MCP (solo lectura)

`listar_variables`, `obtener_lectura`, `obtener_estado_plc`, `consultar_historial`, `comparar_con_rango`, `verificar_coherencia_caudal`, `comparar_con_historico_lvm`.
Cada respuesta incluye unidad, periodo, fuente y si el dato está VIGENTE o DESACTUALIZADO; no inventa datos cuando faltan.

## Próximos pasos

1. Ejecutar la migración `04_migracion_v32.sql`, arrancar el conector v3.2 y verificar los valores nuevos frente a la HMI.
2. Probar `servidor_mcp.py --probar` con datos reales y conectarlo a Claude Desktop.
3. Obtener del responsable del laboratorio el **rango operativo validado** del caudal (hoy 0–140 L/min provisional).
4. Resolver el caso de uso inicial con un agente y registrar preguntas/respuestas como evidencia.
5. Construir el knowledge graph del módulo (tanque → bomba/variador → válvula → caudalímetro; PID → variador; modos) y exponerlo como herramientas MCP.
6. Ampliar a multiagente (consulta, diagnóstico, reporte, coordinador).
7. Evaluación: 20–30 preguntas con respuesta verificada, agente con y sin knowledge graph; métricas de exactitud, latencia, integridad de datos y tasa de errores.

## Caso de uso inicial

Consultar el caudal del laboratorio, recuperar su historial reciente y resumir su evolución comparándolo con un rango establecido y validado por el responsable del laboratorio. El sistema muestra valores, unidades y periodo consultado; si los datos faltan o están desactualizados, lo indica en lugar de inventar resultados.

## Seguridad y alcance

- Todo el sistema es **de solo lectura**: el conector no tiene funciones de escritura y el servidor MCP usa un rol sin permisos de escritura, en sesiones read-only.
- El modelo de IA no puede escribir en salidas, consignas ni registros del PLC.
- No se modifica el programa del PLC, la configuración del CP243-1 ni la HMI.
