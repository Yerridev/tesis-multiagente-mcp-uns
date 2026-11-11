@echo off
chcp 65001 >nul
rem ============================================================
rem  CAPTURA el trafico de la pantalla HMI TPC-2106T (%IP%)
rem  para ver que variables pide. Solo ESCUCHA: no envia nada.
rem  Usa pktmon (incluido en Windows 10/11). Necesita administrador.
rem ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Pidiendo permisos de administrador para capturar trafico...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0.."
set "IP=%~1"
if "%IP%"=="" set /p "IP=IP de la HMI (Enter = 192.168.114.72 caudal, escribe 192.168.114.92 para nivel): "
if "%IP%"=="" set "IP=192.168.114.72"
set "SAL=%CD%\tests\hmi"
if not exist "%SAL%" mkdir "%SAL%"
echo ============================================================
echo  CAPTURA DEL TRAFICO DE LA HMI %IP% (60 segundos)
echo ============================================================
echo.
echo [1/5] Ping a la HMI...
ping -n 2 -w 800 %IP%
echo.
echo [2/5] Preparando el filtro (solo trafico con %IP%)...
pktmon stop >nul 2>&1
pktmon filter remove >nul 2>&1
pktmon filter add HMI -i %IP%
echo.
echo [3/5] Capturando 60 s... (deja la HMI encendida; si puedes, toca sus pantallas/botones)
pktmon start --capture --pkt-size 0 -f "%SAL%\hmi_%IP%.etl"
timeout /t 60 /nobreak
echo.
echo [4/5] Deteniendo y convirtiendo a pcapng...
pktmon stop
pktmon etl2pcap "%SAL%\hmi_%IP%.etl" -o "%SAL%\hmi_%IP%.pcapng"
pktmon filter remove >nul 2>&1
echo.
echo [5/5] Puertos abiertos en la HMI (los mas comunes)...
powershell -NoProfile -Command "foreach($p in 21,23,80,139,445,2343,3580,5000,6000,6001,59110,3363,3537){ $t=New-Object Net.Sockets.TcpClient; $ok=$t.BeginConnect('%IP%',$p,$null,$null).AsyncWaitHandle.WaitOne(600) -and $t.Connected; $t.Close(); if($ok){'  TCP '+$p+' ABIERTO'} }" > "%SAL%\puertos.txt"
type "%SAL%\puertos.txt"
echo.
echo LISTO. Archivos en tests\hmi\ (hmi.pcapng y puertos.txt). Avisame y los analizo.
pause
