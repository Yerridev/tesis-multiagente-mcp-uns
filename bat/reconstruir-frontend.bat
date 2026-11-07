@echo off
cd /d "%~dp0.."
docker compose -f compose.yaml -f compose.override.yaml up -d --build frontend
echo.
echo LISTO. Revisa arriba si hubo errores.
pause
