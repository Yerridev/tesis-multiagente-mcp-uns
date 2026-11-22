@echo off
chcp 65001 >nul
echo ============================================================
echo  VOLCADO DE TEMPERATURA: PLC vs MQTT vs WEB (solo lectura)
echo  1. Lo que el lector publico en MQTT (mcpy-mosquitto, 6 s)
echo  2. Lo que el backend entrega a la web (/signals y /equipment)
echo  3. Las ordenes que la web envio al PLC (/comandos)
echo  Guarda todo en logs\volcado-temperatura.txt
echo ============================================================
cd /d "%~dp0.."
set "OUT=logs\volcado-temperatura.txt"
echo Volcado %date% %time% > "%OUT%"

echo.
echo === 1/3 MQTT: topicos de temperatura-mct09 (6 s) ===
echo. >> "%OUT%"
echo ===== 1. MQTT (lo que publica el lector del Twido) ===== >> "%OUT%"
docker exec mcpy-mosquitto mosquitto_sub -h localhost -t "uss/campus/lab-automatizacion/sl01la07/temperatura-mct09/#" -v -W 6 >> "%OUT%" 2>&1
echo  listo

echo.
echo === 2/3 y 3/3 Backend: senales, equipo y ordenes ===
powershell -NoProfile -Command ^
 "$tok = (Get-Content .env | Where-Object { $_ -like 'SERVICIO_TOKEN=*' }) -replace '^SERVICIO_TOKEN=',''; $h = @{ Authorization = 'Bearer ' + $tok.Trim() };" ^
 "foreach ($u in 'http://127.0.0.1:8080/api/equipment/temp-mct09/signals','http://127.0.0.1:8080/api/equipment/temp-mct09','http://127.0.0.1:8080/api/control/temperatura/estado','http://127.0.0.1:8080/api/control/temperatura/comandos?limit=50') {" ^
 "  Add-Content -Encoding utf8 '%OUT%' ''; Add-Content -Encoding utf8 '%OUT%' ('===== ' + $u + ' =====');" ^
 "  try { (Invoke-RestMethod -Uri $u -Headers $h -TimeoutSec 10 | ConvertTo-Json -Depth 8) | Add-Content -Encoding utf8 '%OUT%'; '  OK ' + $u } catch { ('ERROR: ' + $_.Exception.Message) | Add-Content -Encoding utf8 '%OUT%'; '  ERROR ' + $u } }"

echo.
echo Guardado en %OUT%
echo LISTO. Avisame y lo comparo con lo que lee el PLC.
pause
