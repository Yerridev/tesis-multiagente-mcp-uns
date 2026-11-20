@echo off
chcp 65001 >nul
echo ============================================================
echo  MONITOR EN VIVO - TEMPERATURA (solo lectura)
echo  Cada segundo: lo que manda el PLC vs lo que muestra la WEB
echo  y registra al instante las ORDENES web->PLC y RESPUESTAS PLC->web
echo  Escribe la temperatura del TERMOMETRO + Enter para registrarla
echo  Registro: logs\monitor-temperatura-FECHA.csv  y  .log
echo  Ctrl+C para salir
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
"%~dp0..\.venv\Scripts\python.exe" -u tests\monitor\monitor_temperatura.py
pause
