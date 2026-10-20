# Historiador del UNS — Módulo de caudal MCC-09 (USS)

Fases 2 y 3 de la tesis: guarda todo lo que publica el conector edge en el UNS (Grafana) y lo expone a agentes de IA mediante un servidor MCP de solo lectura.

```
PLC S7-200 ──(enlace 1, solo lectura)──► conector_edge_s7200.py ──MQTT──► Mosquitto (Windows)
                                                                              │
                                              ingestor (Docker) ◄────────────┘
                                                   │
                                              TimescaleDB (Docker) ──► Grafana :3000
                                                   ▲                  └► mcp_servidor/servidor_mcp.py (rol mcp_lector) ──► agente IA
                    importar_lvm.py ───────────────┘  (históricos 2008-2011)
```

> **Módulo de nivel (MicroLogix 1100):** desde el 19-oct-2026 este historiador también recibe el módulo de nivel mediante `conector_edge_ml1100.py` y el servicio `ingestor-nivel`. El servicio guarda las variables con prefijo `nivel-mcn09/` para no mezclarlas con las de caudal. Para el ingestor de caudal no cambia nada: `VAR_PREFIX` vacío equivale al comportamiento original. Guía completa en [`../nivel/README.md`](../nivel/README.md).

## Requisitos
- Docker Desktop.
- Mosquitto en Windows escuchando en la red (en `mosquitto.conf`: `listener 1883 0.0.0.0` y `allow_anonymous true`), porque los contenedores lo alcanzan como `host.docker.internal`.
- Python con `pip install "psycopg[binary]"` para el importador.

## Puesta en marcha
```powershell
cd historiador
copy .env.example .env          # cambia las contraseñas
docker compose up -d --build
docker compose logs -f ingestor # debe decir "MQTT conectado" y "Conectado a la base de datos"
```
Luego arranca el conector en otra terminal: `python conector_edge_s7200.py`.

Grafana: http://localhost:3000 (usuario `admin`, contraseña de `GRAFANA_PASSWORD`) → carpeta **Laboratorio USS** → **Módulo de caudal MCC-09 - UNS**. El selector *Fuente de datos* cambia entre `uns` (en vivo) y `lvm` (históricos).

## Importar los históricos del SCADA original
```powershell
python herramientas\importar_lvm.py "Y:\Downloads\TODO-CAUDAL-PC-XP" --solo-revisar
python herramientas\importar_lvm.py "Y:\Downloads\TODO-CAUDAL-PC-XP" --dsn postgresql://uns_admin:TU_CLAVE@localhost:5432/uns
```
Es idempotente: los archivos duplicados entre carpetas no generan filas repetidas.
Para verlos en Grafana elige fuente `lvm` y un rango de fechas entre 2008 y 2011.

## Servidor MCP (fase 3)
`mcp_servidor/servidor_mcp.py` — se conecta como `mcp_lector` (solo `SELECT`) y además abre cada sesión en modo read-only. No tiene ninguna vía hacia el PLC.

| Herramienta | Qué responde |
|---|---|
| `listar_variables` | Variables del UNS con dirección PLC, unidad, último dato en vivo y cuántos datos históricos tienen |
| `obtener_lectura(variables)` | Último valor, hora, antigüedad y **VIGENTE / DESACTUALIZADO** con el motivo (conector caído, PLC sin conexión, variable que no aplica al modo actual) |
| `obtener_estado_plc` | Conector y PLC, último latido, modo REMOTO/LOCAL, mando PC/HMI, bomba, alarmas de nivel |
| `consultar_historial(variable, minutos / inicio-fin, fuente)` | Estadísticas + serie resumida; `fuente='lvm'` para 2008-2011 |
| `comparar_con_rango(variable, minutos)` | Dentro/fuera del rango de `rangos_validados` y % de muestras fuera; avisa si el rango es provisional |
| `verificar_coherencia_caudal(minutos, tolerancia_lpm)` | PV del PID vs caudalímetro (dos medidas independientes): COHERENTE / INCOHERENTE |
| `comparar_con_historico_lvm(minutos)` | Error y variabilidad del lazo hoy vs. el SCADA original con setpoint parecido |

Instalar y probar (con Docker levantado):
```powershell
.venv\Scripts\activate
pip install -r mcp_servidor\requirements.txt
$env:MCP_DSN = "postgresql://mcp_lector:TU_CLAVE_LECTOR@localhost:5432/uns"   # MCP_READER_PASSWORD del .env
python mcp_servidor\servidor_mcp.py --probar      # ejecuta cada herramienta una vez y muestra el JSON
```
Conectarlo a Claude Desktop: copia el bloque de `mcp_servidor\claude_desktop_config.ejemplo.json` en
`%APPDATA%\Claude\claude_desktop_config.json`, pon tu clave y reinicia Claude Desktop. Prueba con:
*"¿Cuál es el caudal actual, cómo varió en los últimos 5 minutos y está dentro del rango?"*

## Cambios v3.2 del conector (19-oct-2026) — ejecutar la migración una vez
```powershell
Get-Content db\04_migracion_v32.sql | docker exec -i uns-timescaledb psql -U uns_admin -d uns
```
| Antes | Ahora | Motivo |
|---|---|---|
| `pid/kp` (VD100), `pid/ki`, `pid/kd` | `pid/kc` (VD171), `pid/ti`, `pid/td` [min] | En la tabla del lazo (VB159) los offsets 20/24 son **tiempos** Ti/Td, no ganancias |
| `caudal/actual` (AIW0, nunca funcionó: error 0x03) | `caudal/caudalimetro` + `caudal/caudalimetro_raw` (MW3) | Network 11 copia AIW0 en MW3 en cada ciclo; válido en REMOTO |
| `actuadores/variador` (AQW2), `actuadores/valvula_proporcional` (MW5) | `actuadores/variador_pct` (VW8), `actuadores/valvula_pct` (MW25) | Se lee lo **aplicado** a AQW2/AQW0, en %, con el mismo nombre que los `.lvm` |
| `actuadores/potenciometro` siempre | Solo en LOCAL | MW2 y MW3 comparten MB3: en REMOTO MW2 = byte alto de AIW0 |

La migración renombra los datos ya guardados (incluidos los `.lvm`) y borra las lecturas falsas del potenciómetro.

## Tablas
| Tabla | Contenido |
|---|---|
| `mediciones` | Hypertable: `time, variable, valor, unidad, fuente ('uns'/'lvm'), direccion` |
| `mediciones_1min` | Agregado continuo: promedio, mínimo, máximo y muestras por minuto |
| `eventos` | Textos del UNS: ONLINE/OFFLINE, CONECTADO/SIN_CONEXION, heartbeat |
| `variables` | Catálogo publicado por el conector (`descriptivo/variables`) |
| `rangos_validados` | Rango aceptado por variable; **pendiente de validar con el responsable del laboratorio** |

## Seguridad
- El rol `mcp_lector` solo tiene `SELECT`: los agentes de IA no pueden escribir ni borrar.
- Ninguna pieza escribe en el PLC.

## Consultas de prueba
```sql
-- Últimos valores
SELECT DISTINCT ON (variable) variable, valor, unidad, time
FROM mediciones WHERE fuente = 'uns' ORDER BY variable, time DESC;

-- Caudal promedio por minuto en la última hora
SELECT minuto, promedio, minimo, maximo FROM mediciones_1min
WHERE variable = 'caudal/pv_pid' AND fuente = 'uns' AND minuto > now() - interval '1 hour'
ORDER BY minuto;
```

## Supuestos a confirmar
- Mapa de canales de los `.lvm` (inferido de los datos): setpoint, caudal, variador %, válvula %, Kc, Ti, Td y un indicador de modo 0/1.
- Escala del caudal: 140 L/min de fondo de escala (programa del PLC) vs. 141 L/min de la calibración: `verificar_coherencia_caudal` lo pone a prueba.
- Variador y válvula: 0-32000 cuentas = 0-100 % (rango estándar de AQW del S7-200).
- Rango operativo del caudal: **pendiente de validar con el responsable del laboratorio** (hoy 0-140 provisional).
