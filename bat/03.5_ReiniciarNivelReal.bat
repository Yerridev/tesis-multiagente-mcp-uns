@echo off
chcp 65001 >nul
echo ============================================================
echo  REINICIAR NIVEL REAL (MicroLogix 1100 - 192.168.114.9)
echo  1. Comprueba que la planta este en modo REAL
echo  2. Comprueba que el PLC responda en la red
echo  3. Detiene y relanza el LECTOR de nivel (Windows)
echo  4. Reinicia el conector de CONTROL de nivel (Docker, sin cambiar su modo)
echo  5. Muestra las ultimas lineas del log del lector
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
echo === 2/5 Ping al MicroLogix 1100 (192.168.114.9) ===
ping -n 2 192.168.114.9 | find "TTL=" >nul && (echo  PLC responde) || (echo  AVISO: el PLC no responde al ping - revisa cable, red 01.1_ConfigurarRedLaboratorio o que este encendido)

echo.
echo === 3/5 Lector de nivel (conector_edge_ml1100) ===
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'launch_nivel_edge|conector_edge_ml1100' -and $_.ProcessId -ne $PID }; if (-not $p) { '  no habia lector de nivel corriendo' } else { $p | ForEach-Object { '  deteniendo PID ' + $_.ProcessId + '  ' + $_.Name; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }"
timeout /t 3 >nul
echo  arrancando conectores\launch_nivel_edge.ps1 (ventana minimizada, log en logs\nivel_edge.log)
start "LECTOR nivel REAL" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\conectores\launch_nivel_edge.ps1"

echo.
echo === 4/5 Conector de control de nivel (Docker) ===
echo  Se REINICIA con su configuracion actual (no cambia DRY-RUN/REAL ni la IP del PLC)
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
docker restart mcp-connector-nivel
if errorlevel 1 (echo  ERROR al reiniciar mcp-connector-nivel: revisa arriba) else (echo  mcp-connector-nivel reiniciado)
docker logs mcp-connector-nivel --tail 5
echo.
echo === 5/5 Esperando 15 s y mostrando el log del lector ===
timeout /t 15 >nul
powershell -NoProfile -Command "if (Test-Path 'logs\nivel_edge.log') { Get-Content 'logs\nivel_edge.log' -Tail 15 } else { '  aun no hay logs\nivel_edge.log' }"
echo.
echo Si ves lineas con valores (nivel/cm, consigna...) el lector ya publica.
echo Si ves "Sin conexion al PLC", revisa la red y vuelve a correr este bat.
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
