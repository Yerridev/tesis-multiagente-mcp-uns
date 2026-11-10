@echo off
chcp 65001 >nul
echo ============================================================
echo  PLANTA SIMULADA: reinicia SOLO el conector de ordenes de presion
echo  (cFP-2200 virtual 127.0.0.1:6341 · broker Windows 127.0.0.1:1883)
echo  No toca la planta real.
echo ============================================================
cd /d "%~dp0.."
set "PY=C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe"
echo.
echo [1/3] Cerrando conectores de ordenes de presion que sigan vivos...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*conector_control_presion*' -and $_.Name -like 'python*' } | ForEach-Object { '  matando PID ' + $_.ProcessId; Stop-Process -Id $_.ProcessId -Force }"
echo.
echo [2/3] Comprobando el simulador de presion (puerto 6341)...
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 6341 -State Listen -ErrorAction SilentlyContinue) { '  OK: SIM presion escuchando' } else { '  FALTA: el SIM presion no corre. Usa 11-detener-simulacion.bat y 10-simular-planta.bat' }"
echo.
echo [3/3] Abriendo ventana "CONTROL presion a SIM"...
set "PYTHONPATH=%CD%\simulador\psp_shim"
set "CONTROL_PRESION_REAL=1"
start "CONTROL presion a SIM" cmd /k ""%PY%" -u conectores\conector_control_presion.py --cfp 127.0.0.1 --broker 127.0.0.1 --puerto 1883 --habilitado-real"
echo.
echo LISTO. En la ventana nueva debe salir "Control de presion listo (REAL)".
echo Luego manda el setpoint otra vez (16-diag-ordenes.bat debe mostrar ACK).
pause
