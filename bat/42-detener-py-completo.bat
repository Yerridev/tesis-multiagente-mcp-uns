@echo off
chcp 65001 >nul
echo ============================================================
echo  DETENER STACK COMPLETO PYTHON (proyecto mcp-industrial-py)
echo  Baja solo los contenedores mcpy-*. Los datos (volumenes)
echo  se conservan. El original NO se toca.
echo ============================================================
cd /d "%~dp0.."
set "COMPOSE_PROJECT_NAME=mcp-industrial-py"
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
echo.
echo Contenedores mcpy- antes:
docker ps --filter "name=^mcpy-" --format "  {{.Names}}  {{.Status}}"
echo.
docker compose -p mcp-industrial-py -f compose.yaml -f compose.override.yaml --profile core --profile edge --profile simulation --profile monitoring down
echo.
echo Contenedores mcpy- despues (deberia no quedar ninguno):
docker ps --filter "name=^mcpy-" --format "  {{.Names}}  {{.Status}}"
echo.
echo LISTO. Para volver al original, levantalo desde su carpeta como siempre.
pause
