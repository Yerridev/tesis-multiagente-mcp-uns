@echo off
chcp 65001 >nul
echo ============================================================
echo  INSTALAR EL PYTHON DEL PROYECTO (.venv)
echo  Crea tesis-mcp-multiagent-uns\.venv e instala las librerias
echo  de conectores, simuladores y pruebas. Se corre UNA vez por PC.
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar-python.ps1"
echo.
echo LISTO. Revisa arriba lo que hizo.
pause
