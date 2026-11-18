# Scripts `.bat` del proyecto MCP Industrial

Numerados por **prioridad de uso** (el 01 es lo primero que corres en el laboratorio).
Todos muestran en pantalla lo que van haciendo. Se ejecutan con **doble clic**.

> **Regla de oro:** la PLANTA REAL y la PLANTA SIMULADA nunca a la vez.
> Para pasar de una a otra usa **10** (simular) o **11** (volver a real).

---

## 🧰 Instalación (una vez por PC)

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **00-instalar-python** | Crea el Python propio del proyecto (`.venv`) e instala las librerías de `requirements.txt` | **Primero de todo** en una PC nueva, o si un bat dice "FALTA .venv" |
| **29-arranque-automatico** | Rehace el arranque de Windows con los lectores reales (caudal, nivel, presión, temperatura) | Una vez, después del 00. Deja respaldo `.bak` |
| **30-restablecer-admin** | Borra todos los usuarios/sesiones y vuelve a crear el admin del `.env` | Si olvidas la clave del admin o cambias `ADMIN_PASSWORD` |
| **31-sistema-multiagente** | Levanta 4 servidores MCP + 4 agentes analistas + orquestador (solo lectura) | Para usar/probar los agentes; dejar abierta |
| **32-preguntar-agentes** | Hace preguntas al orquestador y muestra plan, informes y veredicto | Con el 31 corriendo |
| **33-evaluar-agentes** | 30 preguntas automaticas, compara con el backend y calcula los indicadores de la tesis; evidencia en la carpeta 05 | Con el 31 corriendo (~15 min) |

> Todo queda **dentro del proyecto**: Python en `.venv\`, logs de los lectores en `logs\` (rotan a los 20 MB),
> chats en `registros\`. Solo presión usa además `C:\Users\KST\NI-DS` (sus DLL de NI) y `C:\Python37-32` (32 bits).

## 🏭 Planta REAL (laboratorio) · uso diario

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **01-red-laboratorio** | Pone IP fija en "Ethernet" (.70, .90, .100), revisa el cable, reinicia Mosquitto de Docker y hace ping a los 4 PLC | **Lo primero** al llegar al laboratorio y conectar el cable. Pide permisos de administrador |
| **02-iniciar-lectores-reales** | Arranca los lectores de presión, temperatura y caudal (y control de temperatura) si no corren | Si al prender la PC algún módulo sale "sin datos". ⚠️ También arranca el control de temperatura de Windows: si lo usas, **no** uses el 04 (los dos se pisarían) |
| **03-temperatura-real** | Revisa el Twido (ping, puerto 502, TwidoSuite abierto) y arranca su lector | Si el SCADA de **temperatura** no tiene datos. El lector de temperatura NO arranca solo con Windows |
| **04-control-temperatura-real** | Arranca el contenedor `mcp-connector-temperatura` y muestra su log | Si las órdenes de **temperatura** dan **Timeout** |

## 🔧 Reconstruir (después de cambios en el código)

Todos **respetan el modo guardado** (real o simulado): no lo pierden.

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **05-reconstruir-todo** | Reconstruye frontend + backend + conector de nivel | Cuando cambió el backend **y** el frontend (lo más común) |
| **06-reconstruir-frontend** | Reconstruye solo la web | Cambios solo visuales (mímicos, iconos, textos). Luego Ctrl+F5 |
| **07-reconstruir-backend** | Reconstruye solo el backend | Cambios solo en el backend (agente, API) |
| **08-recrear-backend** | Reinicia el backend **sin** reconstruir | Para que tome cambios del `.env` (claves, modelos) |
| **09-reconstruir-conector-nivel** | Reconstruye el conector de control de nivel | Cambios en `conector_control_nivel.py` |

## 🧪 Planta SIMULADA (sin tocar los PLC físicos)

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **10-simular-planta** | Para los lectores reales, abre los 4 PLC virtuales + sus conectores y pone el sistema en modo SIMULADO | Para probar SCADA, lienzos y agentes **fuera del laboratorio** |
| **11-detener-simulacion** | Cierra simuladores, vuelve a modo REAL (el control lo decide `.env`) y arranca el control de temperatura | Al terminar de simular, **antes** de trabajar con la planta real |
| **12-estado-simulacion** | Revisa (sin cambiar nada) qué está vivo: simuladores, conectores, puertos, Docker | Si algo de la simulación no responde |
| **13-docker-planta-simulada** | Repite solo el paso de Docker de la simulación | Si Docker Desktop estaba cerrado al correr el 10 |
| **14-reiniciar-control-presion-sim** | Reinicia solo el conector de órdenes de presión (simulado) | Órdenes de **presión** con Timeout en simulación |

## 📊 Pruebas y diagnóstico

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **15-probar-agentes** | 9 preguntas a cada modelo gratis + prueba las 6 herramientas MCP; califica contra los datos reales. Guarda `tests\agente\resultado_*.md` | Para evaluar los agentes (tesis). `--todos` incluye los de pago |
| **16-diag-ordenes** | Muestra en vivo las órdenes (CMD) y sus respuestas (ACK) | Cuando una orden da **Timeout**: CMD sin ACK = conector caído |
| **17-diag-red** | Diagnóstico de la red del laboratorio | Problemas de conexión con los PLC |

## ♻️ Reinicios de la planta REAL (cuando un módulo se cuelga)

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **18-reiniciar-caudal-real** | Mata y relanza el lector/control de caudal (S7-200) | Caudal congelado o "PLC desconectado" |
| **19-reiniciar-presion-nids** | Reinicia la pila NI-DS del cFP-2200 | Presión sin datos y el 20 no lo arregla |
| **20-reiniciar-edge-presion** | Reinicia solo el lector de presión | Presión congelada |
| **21-reiniciar-control-presion-real** | Reinicia el conector de órdenes de presión real | Órdenes de **presión** con Timeout en planta real |

## ☁️ GitHub

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **22-subir-nuestro-repo** | Commit + push a `bvasquezkeysije/tesis-mcp-multiagent-uns` (main) | Guardar avances (recomendado al cerrar el día) |
| **23-subir-repo-yerri** | Commit + push al repo de Yerri (rama `mcp-industrial`) | Compartir con Yerri |
| **24-subir-github** | Commit + push genérico | Respaldo rápido |

## ⚙️ Otros

| Bat | Qué hace | Cuándo usarlo |
|---|---|---|
| **26-vigilar-io-caudal** | Muestra en vivo qué entrada/salida del S7-200 cambia (I0.x, Q0.x, Q1.x) | Para identificar en campo el guardamotor, paro de emergencia, pulsadores |
| **27-capturar-hmi** | Escucha 60 s el tráfico de la HMI TPC-2106T (.72) y prueba sus puertos. Guarda `tests\hmi\hmi.pcapng` | Para descubrir qué variables pide la HMI (no envía nada) |
| **28-hmi-nivel** | Revive la pantalla HMI de nivel (.92): arranca el motor de variables NI, abre el firewall solo para .92 y corre el puente PLC→HMI en **solo lectura** | Para mostrar la HMI de nivel (p. ej. en la defensa). La 1.ª vez con el módulo en LOCAL y detenido |
| **25-ejecutor-mcp** | Ejecuta tareas de `tools\trabajos\*.cmd` mientras la ventana esté abierta | Solo para desarrollo asistido |

### Archivos auxiliares (no se ejecutan a mano)
- `_modo-planta.bat` · lee `.modo-planta` (real/simulado) para que los reconstruir no pierdan el modo
- `simular-planta.ps1`, `estado-simulacion.ps1`, `temperatura-real.ps1`, `instalar-python.ps1`, `arranque-automatico.ps1` · los usan los bats 10, 12, 13, 03, 00 y 29
- `.modo-planta` · modo guardado actual (lo escriben el 10 y el 11)

---

## Flujos típicos

```
LLEGO AL LABORATORIO          PROBAR EN CASA (sin PLC)       CAMBIÉ CÓDIGO
 01 red-laboratorio            10 simular-planta              05 reconstruir-todo
 02 iniciar-lectores-reales    ...pruebas...                  (o 06 si es solo visual)
 03 temperatura-real           11 detener-simulacion
 (15 probar-agentes)

UNA ORDEN DA TIMEOUT
 16 diag-ordenes → ¿llega CMD? ¿vuelve ACK?
   real:     caudal 18 · presión 21 · temperatura 04
   simulado: 12 estado-simulacion → presión 14
```
