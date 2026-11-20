@echo off
chcp 65001 >nul
rem ============================================================
rem  HMI DE NIVEL (TPC-2106T 192.168.114.92): vuelve a mostrar datos
rem  El puente lee el PLC de nivel y llena las variables de la HMI.
rem  Modo SEGURO: --sin-arbitraje = SOLO LECTURA (no escribe nada al PLC)
rem ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Pidiendo permisos de administrador: firewall y servicio de NI...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
set "DIR=%~dp0..\..\modulos-industriales-informacion\MCN\08.0_DESPLIEGUE_LIBRERIA_HMI"
set "PY=%~dp0..\.venv\Scripts\python.exe"
cd /d "%DIR%"
echo ============================================================
echo  HMI DE NIVEL - puente PLC -^> pantalla (solo lectura)
echo  Recomendado: modulo de nivel en LOCAL y detenido la primera vez
echo ============================================================
echo.
echo [1/5] Ping a la HMI de nivel (192.168.114.92) y al PLC (192.168.114.9)...
ping -n 1 -w 800 192.168.114.92 >nul && (echo   HMI responde) || (echo   HMI NO responde: revisa que este encendida)
ping -n 1 -w 800 192.168.114.9  >nul && (echo   PLC responde) || (echo   PLC NO responde: corre 01.1_ConfigurarRedLaboratorio)
echo.
echo [2/5] Motor de variables de NI (NI Variable Engine)...
powershell -NoProfile -Command "$s=Get-Service | Where-Object { $_.Name -like 'NITagger*' -or $_.DisplayName -like '*Variable Engine*' } | Select-Object -First 1; if(-not $s){ '  NO encontrado: hay que instalar el runtime de NI con Variable Engine' } elseif($s.Status -ne 'Running'){ Start-Service $s.Name; '  ' + $s.DisplayName + ': estaba detenido -> ARRANCADO' } else { '  ' + $s.DisplayName + ': corriendo' }"
echo.
echo [3/5] Firewall: abriendo puertos NI solo para la HMI .92...
powershell -NoProfile -ExecutionPolicy Bypass -File "%DIR%\habilitar_firewall_hmi.ps1"
echo.
echo [4/5] Prueba unica del puente (lee el PLC y llena la HMI una vez)...
"%PY%" -u puente_plc_hmi.py --once --sin-arbitraje
echo.
echo   Mira la pantalla de la HMI: deben aparecer el nivel y LOCAL/REMOTO.
echo   (si sigue en cero, reinicia la app de la HMI una vez)
echo.
choice /c SN /m "[5/5] Dejar el puente corriendo continuo? (S/N)"
if errorlevel 2 goto fin
echo.
echo Puente CONTINUO (solo lectura). Cierra esta ventana o Ctrl+C para detenerlo.
"%PY%" -u puente_plc_hmi.py --sin-arbitraje
:fin
echo.
echo LISTO. Revisa arriba lo que hizo.
pause
