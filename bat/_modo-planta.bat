@echo off
rem ============================================================
rem  Lee el modo de la planta guardado (bat\.modo-planta) y prepara
rem  las variables de Docker para NO perderlo al reconstruir.
rem  Lo escriben: 10-simular-planta.bat (simulado) y 11-detener-simulacion.bat (real).
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
rem Broker Mosquitto de Docker (puerto 1884): en la IP del laboratorio si el cable esta conectado
set "MQTT_LAB_IP=127.0.0.1"
for /f %%I in ('powershell -NoProfile -Command "if (Get-NetIPAddress -IPAddress 192.168.114.100 -ErrorAction SilentlyContinue | Where-Object { (Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue).Status -eq 'Up' }) { '192.168.114.100' } else { '127.0.0.1' }"') do set "MQTT_LAB_IP=%%I"
echo Modo de planta guardado: %MODO_ACTUAL%  (se mantiene al reconstruir)
if "%MQTT_LAB_IP%"=="127.0.0.1" (echo Red del laboratorio: SIN CABLE - broker 1884 solo en esta PC; con cable corre 01-red-laboratorio) else (echo Red del laboratorio: OK - broker 1884 en 192.168.114.100)
