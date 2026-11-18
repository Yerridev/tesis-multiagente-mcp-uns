@echo off
chcp 65001 >nul
echo ============================================================
echo  EVALUACION DEL SISTEMA MULTIAGENTE (indicadores de la tesis)
echo  - 30 preguntas automaticas (bateria de 10, repetida 3 veces)
echo  - compara cada respuesta con los valores reales del backend
echo  - evidencia en: 05 - Evaluar desempeno de los agentes MCP\Evidencias
echo  Requiere: planta (simulada o real) + backend + bat 31 ABIERTO
echo  Tarda ~15 min. Usa creditos de OpenRouter (~200 consultas).
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "BACKEND_URL=http://127.0.0.1:8080"
set "ESC=simulada-normal"
set "FALLA="
set /p ESC=Nombre del escenario [Enter = simulada-normal]: 
set /p FALLA=Modulo con falla inyectada (nivel/caudal/presion/temperatura) [Enter = ninguna]: 
echo.
echo Escenario: %ESC%   Falla: %FALLA%
echo Empezando...
if "%FALLA%"=="" ("%PY%" -u tests\evaluacion\evaluar.py --n 30 --escenario "%ESC%") else ("%PY%" -u tests\evaluacion\evaluar.py --n 30 --escenario "%ESC%" --falla %FALLA%)
echo.
echo LISTO. Avisame y reviso la evidencia.
pause
