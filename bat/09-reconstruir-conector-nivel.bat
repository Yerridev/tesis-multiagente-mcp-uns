@echo off
cd /d "%~dp0.."
call "%~dp0_modo-planta.bat"
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
docker compose -p mcp-industrial-py -f compose.yaml -f compose.override.yaml up -d --build connector-nivel
echo.
echo LISTO. Revisa arriba si hubo errores.
pause
