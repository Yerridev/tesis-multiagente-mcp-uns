# Orquestación multiagente — núcleo y experimento

Implementa y compara tres arquitecturas sobre los **mismos 4 servidores MCP** (por stdio, igual que el lienzo) y el **mismo modelo**; la única variable es cómo se organiza el razonamiento. Fundamento: [revisión de la literatura](https://claude.ai/artifact/SLGrGbGfeWrHHnLi4skArE).

| Config | Arquitectura | Peticiones típicas |
|---|---|---|
| **A** | Agente único: un LLM con las 28 herramientas (hasta 10 rondas). Línea base | 2–6 |
| **B** | Multiagente centralizado: **coordinador LLM** planifica (JSON), agentes de equipo en paralelo (solo sus 7 herramientas, hasta 6 rondas), síntesis y **verificador** | 5–12 |
| **C** | Híbrido: **enrutador por reglas** (workflow, sin LLM). Un equipo → su agente responde; varios → agentes en paralelo + síntesis. Con verificador | 3–10 |
| **D** | Multiagente **por roles** (diseño del lienzo, `lienzo/backend/agentes.py`): planificador por reglas → especialistas consulta / diagnóstico / reporte en serie, cada uno con lista blanca de herramientas de todos los equipos → coordinador sin herramientas. Con verificador | 4–20 |

`--sin-verificador` ejecuta B, C y D sin verificador (configuraciones `B-sv`, `C-sv`, `D-sv`) para medir su efecto.

## Archivos

| Archivo | Qué hace |
|---|---|
| `llm.py` | Cliente común (API compatible con OpenAI), ritmo máximo por minuto, reintentos ante 429/5xx, conteo de peticiones y tokens |
| `modelos.json` | Perfiles: `gemini-flash`, `gemini-flash-lite`, `ollama`, `openrouter` (`OPENROUTER_MODEL`, por defecto `openai/gpt-4o-mini`), `claude` (nombre de modelo sobrescribible desde el `.env`) |
| `mcp_pool.py` | Abre los servidores MCP reales de `equipos.json` y expone sus herramientas por equipo |
| `agentes.py` | Bucle de herramientas, prompts comunes, agente de equipo, formato final obligatorio (bloque `json`) |
| `orquestador.py` | Configuraciones A, B y C, coordinador, enrutador, síntesis y verificador |
| `preguntas.json` | 41 preguntas sobre momentos pasados: 10 de tipo 1 (lectura), 23 de tipo 2 (diagnóstico de un equipo = los casos verificados), 8 de tipo 3 (varios equipos) |
| `experimento.py` | Corre modelo × configuración × pregunta, puntúa y resume |

## Cómo correrlo (desde `historiador\`, con Docker encendido)

```powershell
EXPERIMENTO.bat --solo-verdad                                   # 1) revisa la verdad de campo, sin LLM
EXPERIMENTO.bat --modelos openrouter --configs A,B,C,D --preguntas L04,D17,P01  # 2) prueba corta (3 preguntas x 4 configs)
EXPERIMENTO.bat --modelos gemini-flash,gemini-flash-lite        # 3) experimento completo
EXPERIMENTO.bat --continuar logs\experimento\20261029_1530      # reanuda si se corta (limites del nivel gratuito)
EXPERIMENTO.bat --resumen   logs\experimento\20261029_1530      # rehace el resumen
```

Salida en `logs\experimento\<fecha>\`: `resultados.jsonl`, `trazas\*.json` (cada paso y cada salida de herramienta), `resumen.md` y `resumen.csv`.

## Métricas

| Métrica | Definición |
|---|---|
| Exactitud | Tipo 1: valor del bloque json dentro de la tolerancia respecto al dato de la base. Tipos 2 y 3: diagnóstico de cada equipo igual al esperado (tipo 3 exige todos) |
| Exactitud tolerante | Igual, pero buscando el valor o el código en todo el texto (separa errores de razonamiento de errores de formato) |
| Fundamentación | % de cifras de la respuesta presentes en alguna salida real de herramienta (excluye fechas, horas, cifras de la pregunta y enteros 0–10) |
| Costo | Peticiones al modelo, tokens, llamadas a herramientas y latencia |

## Limitaciones conocidas

- Los módulos no se probaron al mismo tiempo: las preguntas de tipo 3 combinan momentos de días distintos.
- Las preguntas de nivel solo son de tipo 1 (no hay casos de diagnóstico verificados de nivel).
- El nivel gratuito de Gemini limita peticiones por minuto y por día: `rpm` en `modelos.json` espacia las peticiones y la corrida se puede reanudar.
