@echo off
chcp 65001 >nul
echo ============================================================
echo  02.6 - LIMPIAR STACKS VIEJOS (una sola vez)
echo  Borra los CONTENEDORES y redes de:
echo    - mcp-industrial      (el original en C#, carpeta ya borrada)
echo    - mcp-industrial-py   (el Python con nombres viejos mcpy-*)
echo  NO borra volumenes (datos) ni imagenes: se pueden limpiar despues.
echo  NO toca el sistema actual (tesis-mcp-multiagente-uns).
echo ============================================================
echo.
echo Contenedores que se van a borrar:
docker ps -a --filter "label=com.docker.compose.project=mcp-industrial" --format "    {{.Names}}  {{.Status}}"
docker ps -a --filter "label=com.docker.compose.project=mcp-industrial-py" --format "    {{.Names}}  {{.Status}}"
echo.
echo Cierra esta ventana para CANCELAR, o
pause
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
echo.
echo [1/2] Bajando mcp-industrial...
docker compose -p mcp-industrial down --remove-orphans
echo.
echo [2/2] Bajando mcp-industrial-py...
docker compose -p mcp-industrial-py down --remove-orphans
echo.
echo Quedan (deberia salir vacio):
docker ps -a --filter "label=com.docker.compose.project=mcp-industrial" --format "    {{.Names}}"
docker ps -a --filter "label=com.docker.compose.project=mcp-industrial-py" --format "    {{.Names}}"
echo.
echo LISTO. Ahora levanta el sistema con 02.0_LevantarSistema.bat
pause
