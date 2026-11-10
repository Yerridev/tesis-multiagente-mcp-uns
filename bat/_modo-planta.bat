@echo off
rem ============================================================
rem  Lee el modo de la planta guardado (bat\.modo-planta) y prepara
rem  las variables de Docker para NO perderlo al reconstruir.
rem  Lo escriben: simular-planta.bat (simulado) y detener-simulacion.bat (real).
rem ============================================================
set "MODO_ACTUAL=real"
if exist "%~dp0.modo-planta" set /p MODO_ACTUAL=<"%~dp0.modo-planta"
if /i "%MODO_ACTUAL%"=="simulado" (
  set "MODO_PLANTA=simulado"
  set "PLC_NIVEL_IP=host.docker.internal"
  set "CONECTOR_MODO=real"
  set "CONTROL_REAL=1"
  set "CONTROL_MODO=Real"
  set "CONTROL_HABILITADOESCRITURA=true"
  set "PRESION_CONTROL_HOST=host.docker.internal"
  set "TEMP_CONTROL_HOST=host.docker.internal"
) else (
  set "MODO_PLANTA=real"
)
echo Modo de planta guardado: %MODO_ACTUAL%  (se mantiene al reconstruir)
