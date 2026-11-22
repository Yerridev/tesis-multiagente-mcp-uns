@echo off
chcp 65001 >nul
echo ============================================================
echo  DIAGNOSTICO DE ORDENES (broker Windows 127.0.0.1:1883)
echo  CMD = orden que manda el backend · ACK = respuesta del conector
echo  Ctrl+C para salir
echo ============================================================
cd /d "%~dp0.."
"%~dp0..\.venv\Scripts\python.exe" -u conectores\diag_ordenes.py
pause
