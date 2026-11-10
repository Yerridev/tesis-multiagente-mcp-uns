@echo off
chcp 65001 >nul
echo ============================================================
echo  PRUEBA DE LOS AGENTES MCP (solo lectura: no toca los PLC)
echo  Misma bateria de 9 preguntas a cada modelo GRATIS y compara
echo  cada respuesta con los datos reales del backend
echo  Resultado: tests\agente\resultado_FECHA.md / .json
echo  Tarda ~5-10 min (pausa de 4 s entre consultas por el limite gratis)
echo ============================================================
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
set "PY=C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe"
echo Revisando librerias del servidor MCP (mcp, httpx)...
"%PY%" -c "import mcp, httpx" 2>nul || "%PY%" -m pip install -q -r mcp\requirements.txt
"C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe" -u tests\agente\prueba_agentes.py %*
echo.
echo LISTO. Avisame y leo el resultado.
pause
