@echo off
chcp 65001 >nul
echo ============================================================
echo  EVALUACION CON FALLAS (solo PLANTA SIMULADA)
echo  - Un modulo a la vez: su PLC virtual deja de responder
echo    (falla de comunicacion) y se hace la bateria de preguntas
echo  - El sistema debe REPORTAR el modulo con falla
echo  - Al terminar cada modulo, la falla se quita sola
echo  - Nunca toca los PLC fisicos: la orden solo la entiende el simulador
echo  Requiere: bat 10 (planta simulada) + bat 31 (agentes) ABIERTOS
echo  Tarda ~4 min por modulo con 10 ejecutados (~16 min en total)
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "BACKEND_URL=http://127.0.0.1:8080"
set "N=10"
set /p N=Ejecutados por modulo [Enter = 10]: 
echo.
echo Empezando: %N% ejecutados por modulo (nivel, caudal, presion, temperatura)...
"%PY%" -u tests\evaluacion\evaluar_fallas.py --n %N%
echo.
echo LISTO. Avisame y reviso la evidencia.
pause
