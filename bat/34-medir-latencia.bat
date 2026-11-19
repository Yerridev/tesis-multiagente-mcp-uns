@echo off
chcp 65001 >nul
echo ============================================================
echo  LATENCIA PLC -^> BACKEND (indicador VD-03)
echo  Mide cuanto tarda cada dato desde que el conector lo lee
echo  del PLC hasta que llega al backend. Dura 2 minutos.
echo  Evidencia en: 05 - Evaluar desempeno ...\Evidencias
echo  Requiere: planta (simulada o real) + Docker (bat 05) corriendo
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "ESC=simulada"
set /p ESC=Escenario [Enter = simulada · escribe real en el laboratorio]: 
echo.
"%PY%" -u tests\evaluacion\medir_latencia.py --segundos 120 --escenario "%ESC%"
echo.
echo LISTO. Avisame y reviso la evidencia.
pause
