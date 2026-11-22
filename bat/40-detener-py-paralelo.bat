@echo off
chcp 65001 >nul
echo ============================================================
echo  DETENER STACK PARALELO PYTHON (proyecto mcp-py)
echo  Solo baja py-backend y py-frontend. El original NO se toca.
echo ============================================================
cd /d "%~dp0.."
docker info >nul 2>&1 || (echo  Docker Desktop no esta corriendo & pause & exit /b 1)
echo.
echo Contenedores py- antes:
docker ps -a --filter "name=py-" --format "  {{.Names}}  {{.Status}}"
echo.
docker compose -p mcp-py -f compose.paralelo.yaml down
echo.
echo Contenedores originales (siguen igual):
docker ps --filter "name=mcp-" --format "  {{.Names}}  {{.Status}}"
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
