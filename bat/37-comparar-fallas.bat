@echo off
chcp 65001 >nul
echo ============================================================
echo  COMPARACION CON FALLAS: configuraciones A y C
echo  (la B ya se evaluo con el bat 35)
echo  - Un modulo a la vez: su PLC virtual deja de responder
echo  - Se mide si cada arquitectura DETECTA y REPORTA la falla
echo  - Solo planta simulada: nunca toca los PLC fisicos
echo  Requiere: bat 10 (planta simulada) + bat 31 (agentes) ABIERTOS
echo  Tarda ~30 min (2 configuraciones x 4 modulos x 10 ejecutados)
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "BACKEND_URL=http://127.0.0.1:8080"
echo.
echo === Configuracion A: agente unico ===
"%PY%" -u tests\evaluacion\evaluar_fallas.py --n 10 --config A
echo.
echo === Configuracion C: enrutador por reglas ===
"%PY%" -u tests\evaluacion\evaluar_fallas.py --n 10 --config C
echo.
echo LISTO. Avisame y reviso la evidencia.
pause
