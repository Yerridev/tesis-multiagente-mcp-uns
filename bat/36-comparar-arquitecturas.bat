@echo off
chcp 65001 >nul
echo ============================================================
echo  EXPERIMENTO COMPARATIVO DE ARQUITECTURAS (A, B y C)
echo  Misma bateria de 10 preguntas, mismo modelo y mismas 28
echo  herramientas MCP; solo cambia como se organizan los agentes:
echo    A = agente unico con todas las herramientas (linea base)
echo    B = orquestador IA + 4 analistas (nuestra arquitectura)
echo    C = enrutador por reglas + 4 analistas
echo  Evidencia en: 05 - Evaluar desempeno ...\Evidencias
echo  Requiere: bat 10 (planta simulada) + bat 31 (agentes) ABIERTOS
echo  Tarda ~45 min con 30 por configuracion. Usa creditos de OpenRouter.
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "BACKEND_URL=http://127.0.0.1:8080"
set "N=30"
set /p N=Ejecutados por configuracion [Enter = 30]: 
echo.
echo Empezando: %N% ejecutados por configuracion (A, B, C)...
"%PY%" -u tests\evaluacion\evaluar_comparacion.py --n %N%
echo.
echo LISTO. Avisame y reviso la evidencia.
pause
