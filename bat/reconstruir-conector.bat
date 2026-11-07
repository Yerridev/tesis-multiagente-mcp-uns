@echo off
cd /d "%~dp0.."
docker compose -f compose.yaml -f compose.override.yaml up -d --build connector-nivel
echo.
echo LISTO. Revisa arriba si hubo errores.
pause
