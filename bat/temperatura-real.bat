@echo off
chcp 65001 >nul
echo ============================================================
echo  TEMPERATURA REAL: revisa la IP del Twido (192.168.114.10)
echo  y arranca su lector si no esta corriendo
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0temperatura-real.ps1"
echo.
echo LISTO. Revisa arriba lo que hizo. Pasame la salida si algo sale en rojo.
pause
