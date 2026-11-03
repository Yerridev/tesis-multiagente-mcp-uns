@echo off
cd /d "%~dp0"
echo Reconstruyendo frontend, backend y conector de nivel...
docker compose -f compose.yaml -f compose.override.yaml up -d --build frontend backend connector-nivel > reconstruir-nivel.log 2>&1
type reconstruir-nivel.log
echo.
echo LISTO. Puedes cerrar esta ventana.
pause
