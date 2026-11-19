@echo off
chcp 65001 >nul
echo ============================================================
echo  STACK COMPLETO PYTHON (proyecto mcp-industrial-py)
echo  - Contenedores propios mcpy-*  y base de datos propia
echo  - Usa los mismos puertos y PLC que el original: por eso
echo    SOLO arranca si el stack ORIGINAL (mcp-*) esta APAGADO
echo  - Web: http://127.0.0.1:8080  (login con admin y la clave
echo    ADMIN_PASSWORD del .env de ESTA carpeta)
echo ============================================================
cd /d "%~dp0.."
set "COMPOSE_PROJECT_NAME=mcp-industrial-py"

echo.
echo === 1/5 Docker en marcha ===
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)

echo.
echo === 2/5 El stack ORIGINAL debe estar apagado ===
set "ORIG="
for /f %%i in ('docker ps -q --filter "name=^mcp-"') do set "ORIG=1"
if defined ORIG (
  echo  ALTO: hay contenedores del original corriendo:
  docker ps --filter "name=^mcp-" --format "    {{.Names}}  {{.Status}}"
  echo  Apagalos primero ^(desde la carpeta del original: docker compose -p mcp-industrial stop^)
  pause & exit /b 1
)
set "PAR="
for /f %%i in ('docker ps -q --filter "name=^py-"') do set "PAR=1"
if defined PAR (
  echo  ALTO: el stack paralelo de solo lectura ^(py-*^) esta corriendo. Bajalo con bat 40.
  pause & exit /b 1
)
echo  OK: el original y el paralelo estan apagados

echo.
echo  Limpiando contenedores mcpy-* creados por error dentro del proyecto del original...
for /f %%i in ('docker ps -aq --filter "label=com.docker.compose.project=mcp-industrial" --filter "name=^mcpy-"') do (echo    borrando %%i & docker rm -f %%i)

echo.
echo === 3/5 Modo de planta y red del laboratorio ===
call "%~dp0_modo-planta.bat"

echo.
echo === 4/5 Construyendo y levantando (perfiles core + edge; la 1a vez tarda) ===
docker compose -p mcp-industrial-py -f compose.yaml -f compose.override.yaml --profile core --profile edge up -d --build
if errorlevel 1 (echo  ERROR al levantar: revisa arriba & pause & exit /b 1)

echo.
echo === 5/5 Estado ===
docker ps --filter "name=^mcpy-" --format "  {{.Names}}  {{.Status}}"
echo.
echo  Web:   http://127.0.0.1:8080
echo  Datos reales: los lectores de Windows ^(bat 02^) publican al broker de
echo  Windows y mcpy-mirror-tesis los copia a este stack.
echo  Agentes: ejecuta el bat 31 DESDE ESTA CARPETA.
echo  Para apagarlo: bat\42-detener-py-completo.bat
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
