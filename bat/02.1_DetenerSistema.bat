@echo off
chcp 65001 >nul
echo ============================================================
echo  DETENER STACK COMPLETO PYTHON (proyecto tesis-mcp-multiagente-uns)
echo  Baja solo los contenedores mcp-*. Los datos (volumenes)
echo  se conservan para la proxima vez.
echo ============================================================
cd /d "%~dp0.."
set "COMPOSE_PROJECT_NAME=tesis-mcp-multiagente-uns"
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
echo.
echo Contenedores mcp- antes:
docker ps --filter "name=^mcp-" --format "  {{.Names}}  {{.Status}}"
echo.
docker compose -p tesis-mcp-multiagente-uns -f compose.yaml -f compose.override.yaml --profile core --profile edge --profile simulation --profile monitoring down
echo.
echo Contenedores mcp- despues (deberia no quedar ninguno):
docker ps --filter "name=^mcp-" --format "  {{.Names}}  {{.Status}}"
echo.
echo LISTO. Para volver a encenderlo usa el levantar sistema.
pause
