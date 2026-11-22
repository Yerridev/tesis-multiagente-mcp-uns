@echo off
chcp 65001 >nul
echo ============================================================
echo  SISTEMA MULTIAGENTE MCP (solo lectura: no toca los PLC)
echo   4 servidores MCP  : nivel 8001, caudal 8002, presion 8003, temperatura 8004
echo   4 agentes analistas (uno por modulo)
echo   1 orquestador     : interprete + veredicto
echo   Coordinacion por MQTT 127.0.0.1:1883 (broker de Windows)
echo   Trazas: registros\agentes\FECHA.jsonl   Logs: logs\agentes-*.log
echo  Requiere el backend levantado (Docker, bat 05 o 13).
echo  Deja esta ventana ABIERTA mientras uses los agentes.
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "BACKEND_URL=http://127.0.0.1:8080"
for /f "tokens=1,* delims==" %%a in ('findstr /b "SERVICIO_TOKEN=" .env') do set "SERVICIO_TOKEN=%%b"
if "%SERVICIO_TOKEN%"=="" echo [AVISO] No hay SERVICIO_TOKEN en el .env: el backend rechazara las consultas.
echo Revisando librerias (mcp, httpx, paho-mqtt)...
"%PY%" -c "import mcp, httpx, paho" 2>nul || "%PY%" -m pip install -q -r mcp\requirements.txt paho-mqtt
echo.
"%PY%" -u mcp\agentes\lanzar.py
pause
