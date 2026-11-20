@echo off
chcp 65001 >nul
echo ============================================================
echo  REINICIAR CAUDAL REAL (S7-200 CPU226 - 192.168.114.7)
echo  1. Comprueba que la planta este en modo REAL
echo  2. Comprueba que el PLC responda en la red
echo  3. Detiene y relanza el LECTOR (Windows)
echo  4. Muestra las ultimas lineas del log
echo ============================================================
cd /d "%~dp0.."
call "%~dp0_modo-planta.bat"
if /i "%MODO_ACTUAL%"=="simulado" (
  echo.
  echo  ALTO: la planta esta en modo SIMULADO. Corre primero 04.1_DetenerSimulacion.bat
  echo  para no mezclar el PLC real con el simulador.
  pause & exit /b 1
)
echo.
echo === 2/4 Ping al S7-200 CPU226 (192.168.114.7) ===
ping -n 2 192.168.114.7 | find "TTL=" >nul && (echo  PLC responde) || (echo  AVISO: el PLC no responde al ping - revisa cable, red 01.1_ConfigurarRedLaboratorio o que este encendido)
echo.
echo === 3/4 Procesos de caudal en Windows ===
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'launch_caudal_(edge|control)|conector_edge_s7200|conector_control_caudal' -and $_.ProcessId -ne $PID }; if (-not $p) { '  no habia procesos de caudal corriendo' } else { $p | ForEach-Object { '  deteniendo PID ' + $_.ProcessId + '  ' + $_.Name; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }"
timeout /t 3 >nul
echo  arrancando conectores\launch_caudal_edge.ps1 (ventana minimizada)
start "launch_caudal_edge" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\conectores\launch_caudal_edge.ps1"
echo.
echo === 4/4 Esperando 15 s y mostrando el log ===
timeout /t 15 >nul
echo  -- logs\caudal_edge.log --
powershell -NoProfile -Command "if (Test-Path 'logs\caudal_edge.log') { Get-Content 'logs\caudal_edge.log' -Tail 10 } else { '  aun no hay logs\caudal_edge.log' }"
echo.
echo Si ves lineas con valores (caudal, setpoint...) el lector ya publica.
echo Si ves "Sin conexion" o errores, revisa la red y vuelve a correr este bat.
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
