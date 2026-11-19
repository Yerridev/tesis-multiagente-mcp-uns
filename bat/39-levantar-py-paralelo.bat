@echo off
chcp 65001 >nul
echo ============================================================
echo  STACK PARALELO PYTHON (proyecto mcp-py) - SOLO LECTURA
echo  - Crea SOLO 2 contenedores: py-backend y py-frontend
echo  - NO toca el stack original (mcp-backend, mcp-frontend, ...)
echo  - Lee el Mosquitto del stack original; nunca envia ordenes
echo  - Web: http://127.0.0.1:8181   (la original sigue en :8080)
echo ============================================================
cd /d "%~dp0.."

echo.
echo === 1/4 Docker en marcha ===
docker info >nul 2>&1 || (echo  Docker Desktop no esta corriendo: abrelo y vuelve a ejecutar & pause & exit /b 1)
echo  OK

echo.
echo === 2/4 El stack ORIGINAL debe estar corriendo (de el se leen los datos) ===
docker network inspect mcp-industrial_application_net >nul 2>&1 || (echo  No existe la red mcp-industrial_application_net: levanta primero el original ^(bat 05 del repo original^) & pause & exit /b 1)
docker ps --filter "name=mcp-mosquitto" --format "  {{.Names}}  {{.Status}}"
echo  Contenedores originales (no se tocan):
docker ps --filter "name=mcp-" --format "    {{.Names}}  {{.Image}}"

echo.
echo === 3/4 Construyendo y levantando py-backend y py-frontend (la 1a vez tarda) ===
docker compose -p mcp-py -f compose.paralelo.yaml up -d --build
if errorlevel 1 (echo  ERROR al levantar el stack paralelo: revisa arriba & pause & exit /b 1)

echo.
echo === 4/4 Estado ===
docker ps --filter "name=py-" --format "  {{.Names}}  {{.Status}}  {{.Ports}}"
echo.
echo  Abre: http://127.0.0.1:8181   (sin login, solo lectura)
echo  Para comparar, la original sigue en su direccion de siempre.
echo  Para bajarlo: bat\40-detener-py-paralelo.bat
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
