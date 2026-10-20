@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" evaluacion\reproducir_casos.py > logs\evaluacion_salida.txt 2>&1
type logs\evaluacion_salida.txt
pause
