# Scripts `.bat` del proyecto tesis-mcp-multiagente-uns

**Nomenclatura:** `0N.0_Nombre` = acción principal del grupo · `0N.1_Nombre`, `0N.2_Nombre`… = acciones del mismo grupo.
Cada grupo empieza con un **separador** (`0N.0-----.bat`, vacío, solo para ver los grupos en el Explorador).
Todos muestran en pantalla lo que van haciendo. Se ejecutan con **doble clic**.

Sistema Docker: proyecto **`tesis-mcp-multiagente-uns`**, contenedores **`mcp-*`** (mcp-backend, mcp-frontend, mcp-mosquitto…).

> **Regla de oro:** la PLANTA REAL y la PLANTA SIMULADA nunca a la vez
> (`04.0` simula · `04.1` vuelve a real).

| Grupo | Bat | Qué hace |
|---|---|---|
| **01 · Instalación** | `01.0_InstalarPython` | Crea `.venv` e instala librerías (primero en una PC nueva) |
| | `01.1_ConfigurarRedLaboratorio` | IP fija 192.168.114.x en el adaptador del laboratorio |
| | `01.2_ArranqueAutomaticoWindows` | Arranque de Windows con los lectores reales |
| | `01.3_RestablecerAdmin` | Vuelve a crear el admin del `.env` (borra usuarios y sesiones) |
| **02 · Sistema (Docker)** | `02.0_LevantarSistema` | Levanta el stack `mcp-*` (web en http://127.0.0.1:8080) |
| | `02.1_DetenerSistema` | Baja el stack `mcp-*` (los datos se conservan) |
| | `02.2_ReconstruirTodo` | Reconstruye frontend + backend + conector de nivel |
| | `02.3_ReconstruirFrontend` | Solo la web |
| | `02.4_ReconstruirBackend` | Solo el backend |
| | `02.5_RecrearBackend` | Recrea el backend para que lea el `.env` (sin reconstruir) |
| | `02.6_LimpiarStacksViejos` | Una vez: borra los contenedores viejos (`mcp-industrial` y `mcp-industrial-py`) |
| **03 · Planta REAL** | `03.0_IniciarLectoresReales` | Arranca los lectores de los 4 PLC |
| | `03.1_TemperaturaReal` | Revisa el Twido y arranca su lector |
| | `03.2_ControlTemperaturaReal` | Arranca el conector de órdenes de temperatura |
| | `03.3_ReconstruirControlTemperatura` | Reconstruye ese conector (bomba al 80 % al Iniciar) |
| | `03.4_ReconstruirConectorNivel` | Reconstruye el conector de nivel |
| | `03.5_ReiniciarNivelReal` | Reinicia lector + control del MicroLogix (nivel) |
| | `03.6_ReiniciarCaudalReal` | Reinicia el conector del S7-200 (caudal) |
| | `03.7_ReiniciarPresionReal` | Reinicia lector + control del cFP-2200 (presión) |
| | `03.8_ReiniciarTemperaturaReal` | Reinicia lector + control del Twido (temperatura) |
| **04 · Planta SIMULADA** | `04.0_SimularPlanta` | 4 PLC virtuales en la PC (sin cable de red) |
| | `04.1_DetenerSimulacion` | Apaga la simulación y vuelve a REAL |
| | `04.2_EstadoSimulacion` | Solo revisa el estado |
| | `04.3_DockerPlantaSimulada` | Repite solo la parte Docker de la simulación |
| | `04.4_ReiniciarControlPresionSim` | Reinicia el conector de presión simulado |
| **05 · Agentes IA (MCP)** | `05.0_SistemaMultiagente` | 4 servidores MCP + analistas + orquestador (dejar abierto) |
| | `05.1_PreguntarAgentes` | Preguntas al orquestador (con el 05.0 corriendo) |
| | `05.2_ProbarModelosAgentes` | Compara modelos LLM con la misma batería |
| | `05.3_EjecutorMCP` | Ejecutor de herramientas MCP |
| **06 · Evaluación (tesis)** | `06.0_EvaluarAgentes` | 30 ejecutados, indicadores VD (con el 05.0) |
| | `06.1_MedirLatencia` | Latencia PLC → backend (VD-03) |
| | `06.2_EvaluarFallas` | Fallas inyectadas, configuración B (planta simulada) |
| | `06.3_CompararArquitecturas` | Configuraciones A / B / C |
| | `06.4_CompararFallas` | Fallas para A y C |
| **07 · Diagnóstico y pruebas** | `07.0_DiagnosticoOrdenes` | Ver CMD / ACK de las órdenes en vivo |
| | `07.1_DiagnosticoRed` | Ping y puertos de los PLC |
| | `07.2_QueWebEstoyViendo` | Qué contenedor sirve la web y qué versión |
| | `07.3_VigilarIOCaudal` | E/S del S7-200 en vivo |
| | `07.4_CapturarHMI` | Captura 60 s del tráfico de la HMI |
| | `07.5_HMINivel` | Puente PLC → HMI de nivel |
| | `07.6_VolcarTemperatura` | Volcado PLC vs MQTT vs web |
| | `07.7_MonitorTemperatura` | Monitor en vivo PLC vs web con log |
| | `07.8_TestEnfriar` | Prueba de enfriamiento de 2 min |
| **08 · GitHub** | `08.0_SubirNuestroRepo` | Commit y push a `bvasquezkeysije/tesis-mcp-multiagent-uns` |
| | `08.1_SubirRepoYerri` | Push a la rama `mcp-industrial` de Yerri |
| | `08.2_SubirAmbosRepos` | Un commit y lo sube a los dos repos (nuestro + Yerri) |

Auxiliares (no se ejecutan solos): `_docker-listo.bat`, `_modo-planta.bat` y los `.ps1`.

**Primera vez tras el cambio de nombres:** `02.6` (borra los stacks viejos `mcp-industrial` y `mcp-industrial-py`) → `02.0` → `01.2`.
