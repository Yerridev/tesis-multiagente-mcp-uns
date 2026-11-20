@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\conectores\diag_red.ps1"
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
