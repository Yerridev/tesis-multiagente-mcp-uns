@echo off
cd /d "%~dp0.."
echo ============================================================
echo  RESTABLECER ADMIN desde el .env (ADMIN_USUARIO / ADMIN_PASSWORD)
echo  OJO: borra TODOS los usuarios y sesiones de la plataforma.
echo  El historial de accesos se conserva.
echo ============================================================
set /p OK=Escribe SI para continuar: 
if /i not "%OK%"=="SI" (echo Cancelado. & pause & exit /b 0)
call "%~dp0_modo-planta.bat"
call "%~dp0_docker-listo.bat" || (pause & exit /b 1)
for /f "tokens=1,* delims==" %%a in ('findstr /b "POSTGRES_USER= POSTGRES_DB=" .env') do set "%%a=%%b"
if "%POSTGRES_USER%"=="" set POSTGRES_USER=postgres
if "%POSTGRES_DB%"=="" set POSTGRES_DB=mcpindustrial
echo.
echo [1/2] Borrando usuarios y sesiones en TimescaleDB...
docker exec mcpy-timescaledb psql -U %POSTGRES_USER% -d %POSTGRES_DB% -c "TRUNCATE seguridad.sesiones, seguridad.usuarios RESTART IDENTITY;"
if errorlevel 1 (echo ERROR: no se pudo borrar. Esta levantado mcpy-timescaledb? & pause & exit /b 1)
echo.
echo [2/2] Recreando el backend para que cree el admin del .env...
docker compose -p mcp-industrial-py -f compose.yaml -f compose.override.yaml up -d --force-recreate backend
echo.
echo Esperando 15 s a que arranque...
timeout /t 15 /nobreak >nul
docker logs --tail 40 mcpy-backend 2>&1 | findstr /i "administrador seguridad"
echo.
echo LISTO. Entra con el usuario y contrasena del .env.
pause
