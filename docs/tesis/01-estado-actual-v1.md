# Estado actual del proyecto de tesis

*Actualizado: 23-oct-2026*

## Tema

**Implementación de una arquitectura multiagente basada en inteligencia artificial para la orquestación e integración de datos industriales utilizando Model Context Protocol (MCP).**

## Objetivo general

Implementar una arquitectura multiagente basada en IA y MCP para facilitar la integración, consulta y análisis de datos industriales.

## Arquitectura y avance por capa

```text
S7-200 + CP243-1 (caudal MCC-09)   MicroLogix 1100 (nivel MCN-09)   cFP-2200 (presión MCP-09)   Twido (temperatura MCT-09)   ✅ los cuatro, solo lectura
   │ python-snap7 (laptop)            │ pycomm3 (laptop)                │ DataSocket (VM Win7)       │ pymodbus (laptop)
   ▼                                  ▼                                 ▼                            ▼
conector_edge_s7200.py v3.2      conector_edge_ml1100.py          conector_edge_cfp2200.py v0.3  conector_edge_twido.py v0.1  ✅
   ⚠️ caudal sin lectura mientras la laptop no tenga la IP .10 (la ocupa el Twido; ver red_laboratorio_plc.md)
   └──────────────────── MQTT (Mosquitto, laptop 192.168.114.12) ───────┘
                                      ▼
UNS  uss/campus/lab-automatizacion/sl01la07/<equipo>/...                                       ✅ caudal-mcc09, nivel-mcn09, presion-mcp09, temperatura-mct09
                                      ▼
Historiador: 4 ingestores + TimescaleDB + Grafana (4 dashboards)                              ✅ + .lvm de caudal 2008-2011 y temperatura 2009-2011
                                      │  rol mcp_lector (solo SELECT)
                                      ▼
servidor_mcp.py · _nivel · _presion · _temperatura + grafos de conocimiento                   ✅ (temperatura: probar con --probar)
                                      ▼
Lienzo multi-equipo (React + agente Gemini) · Claude Desktop                                  ✅
                                      ▼
Orquestación multiagente (consulta, diagnóstico, reporte y coordinador)                        ✅ v1 en el lienzo
Evaluación experimental                                                                        🟡 23 casos: caudal 11, presión 10 (+1 no puntuado), temperatura 2; falta nivel
```

Arranque: `historiador/INICIAR_TODO.bat` (v2) funciona con cualquier subconjunto de equipos encendidos.

## Avance del 23 de octubre: módulo de temperatura

1. **Análisis del material:** respaldo TwidoSuite (`Twido1.xtwd`), proyecto LabVIEW `MCT.lvproj`, diagrama de `scada_mct_04.vi` exportado a HTML, manual fotografiado (43 p.) con planos de bornera, PLC, módulos analógicos y variador.
2. **Puesta en marcha:** el PLC estaba sano; faltaban el pulso de inicio y los parámetros (el Twido pierde SP/Kp/Ti/Td al apagarse). Se arrancó por Modbus desde la laptop para aislar fallas.
3. **Altivar 11 (gama Asia) en mando local de fábrica:** `FUn → tCC → ACt` LOC → **2C** y `AIt` 5U → **10U**; la bomba ahora obedece al PLC. Es la misma causa probable del lazo abierto de presión.
4. **HMI y SCADA recuperados:** la cadena real es HMI → variables compartidas en la PC `.100` → `MOD_TEMP.exe` → DataSocket `opc://` → *Industrial Automation OPC Servers* 5.1 (objeto Modbus `temp`) → Twido. Se instaló el OPC Server, se creó el objeto (con **PollRate `0:01`**: Lookout mide el tiempo en días y `1.0` congelaba la lectura) y se desplegaron `LIB_PC`/`LIB_HMI`.
5. **Escala del SP corregida** con el diagrama del SCADA: el SP va en cuentas 0–4095, no en 0–10000.
6. **Seguridad:** el tanque principal se calentó con el lazo detenido y hubo olor a quemado: relé de estado sólido FOTEK **sin disipador**, en revisión. El MCP detecta este caso (`CALENTAMIENTO_SIN_ORDEN`).
7. **Integración completa:** `tags_temperatura.yaml`, conector Modbus, `ingestor-temperatura`, migración `07`, dashboard, `servidor_mcp_temperatura.py`, `grafo_mct09.json`, lienzo e históricos `.lvm` 2009–2011.
8. **Red:** el Twido ocupa la `.10`; la laptop pasó a `.12` (caudal queda pendiente de segmento aparte o de reconfigurar el enlace 1 del CP243-1).

Detalle: `temperatura/README.md`.

## Avance del 20–21 de octubre: módulo de presión

1. **Recuperación del cFP-2200** (parado desde 2018): interruptores DIP, bootline de VxWorks corrupta (reseteada por consola serial), *Format Disk* + reinstalación de FieldPoint 6.0.2, restauración de `startup.rtexe` por FTP y redespliegue de las variables `DATOS_PAC` y `pid`. Procedimiento: `presion/RECUPERACION_cFP2200.md`.
2. **Vía de lectura sin la PC del laboratorio:** el cFP habla NI-PSP (propietario) y no tiene Modbus configurado; se instaló el driver NI-FieldPoint en la VM Windows 7 y el conector lee por DataSocket (ActiveX) y publica en MQTT.
3. **Integración completa:** migración `06_presion_v01.sql`, `ingestor-presion`, servidor MCP v1.0 con `diagnosticar_presion`, grafo `grafo_mcp09.json`, dashboard Grafana y entrada en el lienzo.
4. **Escala** `psi = (mA − 4)/16 × 87` validada contra la HMI (manómetro averiado).
5. **Hallazgo:** el Altivar 11 toma la velocidad de su perilla frontal e ignora la consigna 0–10 V del PID; el MCP lo detecta como `ACTUADOR_NO_RESPONDE`. Corregirlo requiere al responsable del laboratorio.
6. **Robustez:** conector v0.3 (tras un cierre de Python en la VM) con reinicio automático; `INICIAR_TODO` v2 tolerante a equipos apagados.

Detalle: `presion/README.md`, `presion/pruebas_20261021.md`.

## Mapa de variables confirmado (caudal)

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

Mapas de nivel y presión: `nivel/README.md` y `presion/README.md` §4.

## Servidores MCP (solo lectura)

| Equipo | Servidor | Diagnóstico propio |
|---|---|---|
| Caudal | `servidor_mcp.py` | `verificar_coherencia_caudal`, `comparar_con_historico_lvm`, `diagnosticar_lazo` |
| Nivel | `servidor_mcp_nivel.py` | `diagnosticar_nivel` |
| Presión | `servidor_mcp_presion.py` v1.0 | `diagnosticar_presion` |
| Temperatura | `servidor_mcp_temperatura.py` v1.0 | `diagnosticar_temperatura` |

Comunes: `listar_variables`, `obtener_lectura`, `obtener_estado_plc`, `consultar_historial`, `comparar_con_rango`, `consultar_grafo`. Cada respuesta incluye unidad, periodo, fuente y si el dato está VIGENTE o DESACTUALIZADO; no inventa datos cuando faltan.

## Próximos pasos

0. **Temperatura:** reparar/reemplazar el relé de estado sólido (con disipador), contrastar la escala con termómetro, respaldar el programa real del Twido (subir, no descargar) y licencia del OPC Server. **Caudal:** decidir cómo recuperar la IP `.10`. **Presión:** ✅ resuelto el 24-oct (Altivar `tCC=2C`, `LSr=tEr`, `AIt=10U` e Input 3 del AIO-610 en voltios); falta la prueba remota completa 5 → 10 → 20 psi.

1. **Presión:** consigna del Altivar por AI1 con el responsable del laboratorio; repetir la prueba remota (SP 5 → 10 → 20 psi); verificar escala con manómetro.
2. Casos de evaluación de nivel en `evaluacion/reproducir_casos.py` (caudal 11, presión 10 y temperatura 2 ya incluidos; correr `EVALUAR_CASOS.bat`).
3. Importar los `.lvm` históricos de nivel (2008–2012) y presión (2008–2009).
4. Obtener del responsable del laboratorio los **rangos operativos validados** (caudal 0–140 L/min provisional; presión 3–40 psi del fabricante).
5. Evaluar la orquestación multiagente v1 (consulta, diagnóstico, reporte y coordinador) frente al agente único.
6. Siguiente equipo: módulo de temperatura (INDUCONTROL TEMPERATURA).
7. Evaluación: 20–30 preguntas con respuesta verificada, agente con y sin knowledge graph; métricas de exactitud, latencia, integridad de datos y tasa de errores.

## Caso de uso inicial

Consultar el caudal del laboratorio, recuperar su historial reciente y resumir su evolución comparándolo con un rango establecido y validado por el responsable del laboratorio. El sistema muestra valores, unidades y periodo consultado; si los datos faltan o están desactualizados, lo indica en lugar de inventar resultados.

## Seguridad y alcance

- Todo el sistema es **de solo lectura**: los conectores no tienen funciones de escritura y los servidores MCP usan un rol sin permisos de escritura, en sesiones read-only.
- El modelo de IA no puede escribir en salidas, consignas ni registros de los controladores.
- No se modifica el programa de los controladores, la configuración del CP243-1 ni las HMI. Excepciones registradas: el 23-oct-2026 se cambió el **Altivar del módulo de temperatura** a mando por bornes (`tCC=2C`, `LSr=tEr`, `AIt=10U`), como lo exige el diseño original, y en la PC del laboratorio se instaló el OPC Server y se desplegaron las variables del SCADA de temperatura. El 24-oct-2026 se hizo lo mismo con el **Altivar de presión** y se devolvió el **Input 3 del cFP-AIO-610** a voltios (configuración original de Inducontrol). En el cFP-2200 solo se restauró la configuración y el programa originales.
