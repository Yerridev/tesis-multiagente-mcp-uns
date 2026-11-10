@echo off
cd /d "%~dp0.."
call "%~dp0_modo-planta.bat"
echo Reconstruyendo frontend, backend y conector de nivel...
docker compose -f compose.yaml -f compose.override.yaml up -d --build frontend backend connector-nivel
echo.
echo LISTO. Puedes cerrar esta ventana.
pause
