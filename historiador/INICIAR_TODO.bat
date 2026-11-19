@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar_arquitectura.ps1"
echo.
echo Listo. Revisa logs\arranque.log
pause
