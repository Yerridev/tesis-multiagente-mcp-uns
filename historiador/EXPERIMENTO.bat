@echo off
rem Experimento de orquestacion multiagente (A agente unico / B coordinador LLM / C hibrido).
rem Requiere Docker con TimescaleDB corriendo. Argumentos opcionales: ver orquestacion\README.md
rem   EXPERIMENTO.bat --solo-verdad
rem   EXPERIMENTO.bat --modelos gemini-flash --preguntas L04,D17,P01
cd /d "%~dp0"
".venv\Scripts\python.exe" -c "import openai, mcp" 2>nul || ".venv\Scripts\python.exe" -m pip install -q "openai>=1.40" "mcp>=1.9"
".venv\Scripts\python.exe" -m orquestacion.experimento %*
pause
