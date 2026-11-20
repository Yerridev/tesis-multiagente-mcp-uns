@echo off
chcp 65001 >nul
echo ============================================================
echo  RECONSTRUIR SOLO EL FRONTEND (no toca backend ni simulacion)
echo ============================================================
cd /d "%~dp0.."
call "%~dp0_modo-planta.bat"
echo.
echo Construyendo y reiniciando el contenedor del frontend...
rem --no-deps: NO recrea el backend (si no, volveria a planta REAL)
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
docker compose -p tesis-mcp-multiagente-uns -f compose.yaml -f compose.override.yaml up -d --build --no-deps frontend
echo.
echo LISTO. Refresca el navegador (Ctrl+F5). El modo sigue en: %MODO_ACTUAL%
pause
