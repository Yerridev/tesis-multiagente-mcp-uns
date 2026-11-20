@echo off
cd /d "%~dp0.."
call "%~dp0_modo-planta.bat"
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
echo Recreando mcp-backend (proyecto tesis-mcp-multiagente-uns) para que lea el .env...
docker compose -p tesis-mcp-multiagente-uns -f compose.yaml -f compose.override.yaml up -d backend
echo.
echo Esperando 10 s y mostrando el log del backend...
timeout /t 10 >nul
docker logs --tail 15 mcp-backend
echo.
echo LISTO. Revisa arriba si hubo errores.
pause
