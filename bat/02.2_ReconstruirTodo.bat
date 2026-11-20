@echo off
cd /d "%~dp0.."
call "%~dp0_modo-planta.bat"
echo Reconstruyendo frontend, backend y conector de nivel...
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
docker compose -p tesis-mcp-multiagente-uns -f compose.yaml -f compose.override.yaml up -d --build frontend backend connector-nivel
echo.
echo LISTO. Puedes cerrar esta ventana.
pause
