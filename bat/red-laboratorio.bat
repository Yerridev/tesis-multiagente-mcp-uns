@echo off
chcp 65001 >nul
rem ============================================================
rem  RED DEL LABORATORIO en el adaptador "Ethernet" (IP fija)
rem    192.168.114.70  -> origen autorizado por el CP243-1 (caudal)
rem    192.168.114.90  -> IP extra del laboratorio
rem    192.168.114.100 -> broker MQTT de Docker (puerto 1884)
rem  Mascara 255.255.255.0, sin puerta de enlace.
rem  Para volver a DHCP: ncpa.cpl > Ethernet > IPv4 > "Obtener automaticamente".
rem ============================================================
set "ADAPTADOR=Ethernet"

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Pidiendo permisos de administrador para cambiar la IP...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================================
echo  RED DEL LABORATORIO en "%ADAPTADOR%" (IP fija 192.168.114.x)
echo ============================================================
echo.
echo [1/4] IP principal 192.168.114.70 / 255.255.255.0 (sin puerta de enlace)...
netsh interface ipv4 set address name="%ADAPTADOR%" source=static address=192.168.114.70 mask=255.255.255.0
if %errorlevel% neq 0 (
  echo   ERROR: no se pudo cambiar. Revisa que el adaptador se llame "%ADAPTADOR%" en ncpa.cpl
  goto fin
)
echo   OK
echo.
echo [2/4] IP adicional 192.168.114.90...
netsh interface ipv4 add address name="%ADAPTADOR%" address=192.168.114.90 mask=255.255.255.0
echo [3/4] IP adicional 192.168.114.100 (broker MQTT de Docker)...
netsh interface ipv4 add address name="%ADAPTADOR%" address=192.168.114.100 mask=255.255.255.0
echo.
echo   esperando 3 s a que Windows aplique las IP...
timeout /t 3 /nobreak >nul
echo.
echo [4/4] Reiniciando Mosquitto de Docker para que vuelva a escuchar en 192.168.114.100:1884...
docker info >nul 2>&1
if %errorlevel% neq 0 (
  echo   Docker no esta corriendo: se aplicara cuando lo abras ^(no hace falta nada mas^)
) else (
  docker restart mcp-mosquitto
)
echo.
echo ===================== IP actuales de "%ADAPTADOR%" =====================
netsh interface ipv4 show addresses name="%ADAPTADOR%"
echo.
echo Probando los PLC (1 ping cada uno):
for %%P in (192.168.114.7 192.168.114.8 192.168.114.9 192.168.114.10) do (
  ping -n 1 -w 700 %%P >nul && (echo   %%P  responde) || (echo   %%P  sin respuesta)
)

:fin
echo.
echo LISTO. Revisa arriba lo que hizo. Para DHCP usa ncpa.cpl.
pause
