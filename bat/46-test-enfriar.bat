@echo off
chcp 65001 >nul
echo ============================================================
echo  46 - TEST ENFRIAR (modulo temperatura, 2 minutos)
echo  Setpoint 0 C (resistencia OFF), bomba 80 %%, inicio PC.
echo  El enfriador prende a los ~2 min. Al final restaura todo.
echo  ANTES: selector CONTROLADOR en PC, tanques con agua.
echo  MIRA: que la bomba suene y el variador marque Hz.
echo ============================================================
cd /d "%~dp0.."
set "PY=%~dp0..\.venv\Scripts\python.exe"
echo.
echo Ejecutando: tests\temperatura\test_enfriar.py
echo.
"%PY%" -u tests\temperatura\test_enfriar.py
echo.
echo FIN. Pasame lo que salio en pantalla.
pause
