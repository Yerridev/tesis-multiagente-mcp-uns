@echo off
rem Abre los 4 simuladores en ventanas separadas. Ejecutar desde la raiz del proyecto.
set PY=C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe
cd /d "%~dp0.."
start "SIM temperatura" "%PY%" -m simulador.temperatura
start "SIM caudal"      "%PY%" -m simulador.caudal
start "SIM nivel"       "%PY%" -m simulador.nivel
start "SIM presion"     "%PY%" -m simulador.presion
