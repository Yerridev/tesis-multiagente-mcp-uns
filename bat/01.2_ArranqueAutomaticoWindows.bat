@echo off
chcp 65001 >nul
echo ============================================================
echo  ARRANQUE AUTOMATICO DE WINDOWS: lectores reales de los 4 PLC
echo  (caudal, nivel, presion lectura+control, temperatura lectura)
echo  Reemplaza MCP-INDUSTRIAL-conectores.cmd (deja respaldo .bak)
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0arranque-automatico.ps1"
echo.
echo LISTO. Revisa arriba lo que hizo.
pause
