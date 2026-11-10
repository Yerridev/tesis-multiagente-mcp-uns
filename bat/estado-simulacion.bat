@echo off
chcp 65001 >nul
echo ============================================================
echo  ESTADO DE LA PLANTA SIMULADA (solo revisa, no cambia nada)
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0estado-simulacion.ps1"
echo.
pause
