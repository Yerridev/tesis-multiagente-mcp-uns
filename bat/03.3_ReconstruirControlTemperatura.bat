@echo off
chcp 65001 >nul
echo ============================================================
echo  03.3 - RECONSTRUIR CONTROL DE TEMPERATURA (stack PY)
echo  Cambio: al dar Iniciar ahora pone la BOMBA al 80 %% (%%MW10)
echo  Contenedor: mcp-connector-temperatura (proyecto tesis-mcp-multiagente-uns)
echo ============================================================
cd /d "%~dp0.."
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
echo.
echo [1/3] Reconstruyendo y levantando el conector...
docker compose -p tesis-mcp-multiagente-uns -f compose.yaml -f compose.override.yaml -f compose.temperatura-real.yaml up -d --build --no-deps connector-temperatura
echo.
echo   esperando 5 s...
timeout /t 5 /nobreak >nul
echo.
echo [2/3] Estado:
docker ps -a --filter name=mcp-connector-temperatura --format "  {{.Names}}  ->  {{.Status}}"
echo.
echo [3/3] Ultimas lineas del contenedor:
docker logs --tail 20 mcp-connector-temperatura
echo.
echo LISTO. Ve a la web ^> Temperatura ^> Iniciar. La bomba debe girar.
pause
