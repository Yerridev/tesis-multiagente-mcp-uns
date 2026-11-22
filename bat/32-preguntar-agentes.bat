@echo off
chcp 65001 >nul
echo ============================================================
echo  PREGUNTAR AL SISTEMA MULTIAGENTE
echo  Antes abre el 31-sistema-multiagente (y dejalo corriendo).
echo  Escribe tu pregunta o deja vacio para "Como esta la planta ahora?"
echo  Escribe "salir" para terminar.
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\.venv\Scripts\python.exe"
:otra
echo.
set "P="
set /p P=Pregunta: 
if /i "%P%"=="salir" exit /b 0
if "%P%"=="" set "P=Como esta la planta ahora?"
echo Consultando a los agentes...
"%PY%" -u mcp\agentes\orquestador.py "%P%"
goto otra
