@echo off
chcp 65001 >nul
echo ============================================================
echo  DETENER PLANTA SIMULADA (PLC virtuales + sus conectores)
echo ============================================================
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'simulador\.(temperatura|caudal|nivel|presion)' -or ($_.CommandLine -match 'conector_(edge|control)_\w+\.py' -and $_.CommandLine -match '--(plc|cfp) 127\.0\.0\.1') };" ^
  "if (-not $p) { Write-Host '  no habia nada de la simulacion corriendo' };" ^
  "foreach ($x in $p) { Write-Host ('  deteniendo PID ' + $x.ProcessId + '  ' + ([regex]::Match($x.CommandLine, '(simulador\.\w+|conector_\w+\.py)')).Value); Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue }"
echo.
echo === Backend y control de nivel de vuelta a la planta REAL (Docker) ===
set MODO_PLANTA=real
> "%~dp0.modo-planta" echo real
echo   modo guardado en bat\.modo-planta = real
set PLC_NIVEL_IP=192.168.114.9
rem El modo de control real (CONECTOR_MODO, CONTROL_REAL, CONTROL_MODO...) lo decide .env:
rem se BORRAN de esta ventana para que no lo pisen (antes forzaba dry-run y el PLC no obedecia).
set CONECTOR_MODO=
set CONTROL_REAL=
set CONTROL_MODO=
set CONTROL_HABILITADOESCRITURA=
echo   control de nivel: modo tomado de .env
set PRESION_CONTROL_HOST=mosquitto
set TEMP_CONTROL_HOST=mosquitto
docker compose -f compose.yaml -f compose.override.yaml up -d backend connector-nivel
echo   arrancando el control real de temperatura (mcp-connector-temperatura)...
docker start mcp-connector-temperatura
echo.
echo Las ventanas negras de la simulacion quedan abiertas sin proceso: puedes cerrarlas.
echo Para volver a leer la planta REAL ejecuta: bat\iniciar-lectores.bat
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
