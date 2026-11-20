@echo off
chcp 65001 >nul
echo ============================================================
echo  REINICIAR TEMPERATURA REAL (Twido TWDLCAE40DRF - 192.168.114.10)
echo  1. Comprueba que la planta este en modo REAL
echo  2. Comprueba que el PLC responda en la red
echo  3. Detiene y relanza el LECTOR (Windows)
echo  4. Reinicia el conector de CONTROL (mcp-connector-temperatura, Docker)
echo  5. Muestra las ultimas lineas del log
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
echo === 2/5 Ping al Twido TWDLCAE40DRF (192.168.114.10) ===
ping -n 2 192.168.114.10 | find "TTL=" >nul && (echo  PLC responde) || (echo  AVISO: el PLC no responde al ping - revisa cable, red 01.1_ConfigurarRedLaboratorio o que este encendido)
echo.
echo === 3/5 Procesos de temperatura en Windows ===
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'launch_temperatura_edge|conector_edge_twido' -and $_.ProcessId -ne $PID }; if (-not $p) { '  no habia procesos de temperatura corriendo' } else { $p | ForEach-Object { '  deteniendo PID ' + $_.ProcessId + '  ' + $_.Name; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }"
timeout /t 3 >nul
echo  arrancando conectores\launch_temperatura_edge.ps1 (ventana minimizada)
start "launch_temperatura_edge" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\conectores\launch_temperatura_edge.ps1"
echo.
echo === 4/5 Conector de control (Docker) ===
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
docker restart mcp-connector-temperatura
if errorlevel 1 (echo  ERROR al reiniciar mcp-connector-temperatura: revisa arriba) else (echo  mcp-connector-temperatura reiniciado)
docker logs mcp-connector-temperatura --tail 5
echo.
echo === 5/5 Esperando 15 s y mostrando el log ===
timeout /t 15 >nul
echo  -- logs\temperatura_edge.log --
powershell -NoProfile -Command "if (Test-Path 'logs\temperatura_edge.log') { Get-Content 'logs\temperatura_edge.log' -Tail 10 } else { '  aun no hay logs\temperatura_edge.log' }"
echo.
echo Si ves lineas con valores (temperatura principal/enfriador) el lector ya publica.
echo Si ves "Sin conexion" o errores, revisa la red y vuelve a correr este bat.
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
