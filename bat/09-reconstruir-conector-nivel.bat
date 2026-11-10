@echo off
cd /d "%~dp0.."
call "%~dp0_modo-planta.bat"
docker compose -f compose.yaml -f compose.override.yaml up -d --build connector-nivel
echo.
echo LISTO. Revisa arriba si hubo errores.
pause
