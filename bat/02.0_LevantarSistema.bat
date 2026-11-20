@echo off
chcp 65001 >nul
echo ============================================================
echo  LEVANTAR EL SISTEMA (proyecto tesis-mcp-multiagente-uns)
echo  - Contenedores mcp-*  y base de datos propia
echo  - Web: http://127.0.0.1:8080  (login con admin y la clave
echo    ADMIN_PASSWORD del .env)
echo ============================================================
cd /d "%~dp0.."
set "COMPOSE_PROJECT_NAME=tesis-mcp-multiagente-uns"

echo.
echo === 1/5 Docker en marcha ===
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)

echo.
echo === 2/5 Stacks viejos (mcp-industrial / mcp-industrial-py) ===
set "VIEJO="
for /f %%i in ('docker ps -aq --filter "label=com.docker.compose.project=mcp-industrial"') do set "VIEJO=1"
for /f %%i in ('docker ps -aq --filter "label=com.docker.compose.project=mcp-industrial-py"') do set "VIEJO=1"
if defined VIEJO (
  echo  ALTO: todavia existen contenedores de los stacks viejos y usan los mismos nombres y puertos:
  docker ps -a --filter "label=com.docker.compose.project=mcp-industrial" --format "    {{.Names}}  {{.Status}}"
  docker ps -a --filter "label=com.docker.compose.project=mcp-industrial-py" --format "    {{.Names}}  {{.Status}}"
  echo  Corre primero 02.6_LimpiarStacksViejos.bat
  pause & exit /b 1
)
echo  OK: no hay stacks viejos

echo.
echo === 3/5 Modo de planta y red del laboratorio ===
call "%~dp0_modo-planta.bat"

echo.
echo === 4/5 Construyendo y levantando (perfiles core + edge; la 1a vez tarda) ===
docker compose -p tesis-mcp-multiagente-uns -f compose.yaml -f compose.override.yaml --profile core --profile edge up -d --build
if errorlevel 1 (echo  ERROR al levantar: revisa arriba & pause & exit /b 1)

echo.
echo === 5/5 Estado ===
docker ps --filter "name=^mcp-" --format "  {{.Names}}  {{.Status}}"
echo.
echo  Web:   http://127.0.0.1:8080
echo  Datos reales: los lectores de Windows ^(bat 03.0^) publican al broker de
echo  Windows y mcp-mirror-tesis los copia a este stack.
echo  Agentes: ejecuta el bat 05.0 DESDE ESTA CARPETA.
echo  Para apagarlo: bat\02.1_DetenerSistema.bat
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
