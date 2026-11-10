@echo off
chcp 65001 >nul
echo ============================================================
echo  CONTROL REAL DE TEMPERATURA (contenedor mcp-connector-temperatura)
echo  Recibe las ordenes del SCADA y escribe %%M30 / %%MW100 en el Twido
echo ============================================================
cd /d "%~dp0.."
echo.
echo [1/3] Estado actual del contenedor:
docker ps -a --filter name=mcp-connector-temperatura --format "  {{.Names}}  ->  {{.Status}}"
echo.
echo [2/3] Arrancandolo (si estaba detenido por la planta simulada)...
docker start mcp-connector-temperatura
if %errorlevel% neq 0 (
  echo   no existia: lo creo con compose.temperatura-real.yaml
  docker compose -f compose.yaml -f compose.override.yaml -f compose.temperatura-real.yaml up -d --build --no-deps connector-temperatura
)
echo.
echo   esperando 5 s...
timeout /t 5 /nobreak >nul
docker ps -a --filter name=mcp-connector-temperatura --format "  {{.Names}}  ->  {{.Status}}"
echo.
echo [3/3] Ultimas lineas del contenedor (si sale un error, pasamelo):
docker logs --tail 20 mcp-connector-temperatura
echo.
echo LISTO. Ahora manda el setpoint otra vez desde el SCADA (rango 15-50 C, selector en PC).
pause
