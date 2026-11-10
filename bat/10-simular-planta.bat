@echo off
chcp 65001 >nul
echo ============================================================
echo  PLANTA SIMULADA: 4 PLC virtuales + conectores a 127.0.0.1
echo  (no toca los PLC fisicos del laboratorio)
echo ============================================================
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0simular-planta.ps1"
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
