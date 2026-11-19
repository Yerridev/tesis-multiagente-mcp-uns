@echo off
REM Conector del modulo de presion (cFP-2200) en la VM Windows 7. Si el proceso se cierra, se reinicia en 10 s.
REM Uso: doble clic (o: CONECTOR_CFP2200.bat 192.168.114.12). Ctrl+C dos veces para detenerlo.
cd /d "%~dp0"
set BROKER=%1
if "%BROKER%"=="" set BROKER=192.168.114.12
:inicio
echo [%date% %time%] Iniciando conector cFP-2200 -> mqtt://%BROKER%
python conector_edge_cfp2200.py --broker %BROKER%
echo [%date% %time%] El conector termino (codigo %errorlevel%). Reinicio en 10 s... >> conector_cfp2200_fallas.log
echo El conector se detuvo. Reinicio en 10 s (Ctrl+C para salir)...
timeout /t 10 /nobreak >nul
goto inicio
