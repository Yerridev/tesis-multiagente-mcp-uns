param([switch]$SoloDocker)   # -SoloDocker: repite solo el paso 6 (Docker) sin tocar simuladores ni conectores
# =====================================================================
#  PLANTA SIMULADA: 4 PLC virtuales (Python) + conectores apuntando a 127.0.0.1
#  Los agentes, el backend, los lienzos y los mimicos (modo REAL) reciben estos
#  datos por el MISMO camino que la planta real: conector -> MQTT -> backend -> MCP.
#  Nada de esto toca los PLC fisicos del laboratorio.
# =====================================================================
$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $raiz '.venv\Scripts\python.exe'
$ml1100 = Join-Path $raiz 'conectores\conector_edge_ml1100.py'
$con  = Join-Path $raiz 'conectores'
$shim = Join-Path $raiz 'simulador\psp_shim'
# Broker Windows (lo espeja mirror-tesis al stack Docker): lectura y ordenes de la planta simulada
$brokerWin = '127.0.0.1';      $puertoWin = 1883

function Paso($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ventana($titulo, $argumentos) {
  # Cada proceso en su propia ventana (cmd /k) para ver su salida y sus errores
  $linea = "title $titulo && `"$py`" -u $argumentos"
  Start-Process cmd.exe -ArgumentList '/k', $linea -WorkingDirectory $raiz | Out-Null
  Write-Host "  abierto: $titulo"
}

function DockerListo {
  docker info *> $null
  if ($LASTEXITCODE -eq 0) { return $true }
  Write-Host '  Docker Desktop no esta corriendo: lo abro y espero (hasta 3 min)...' -ForegroundColor Yellow
  $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
  if (Test-Path $exe) { Start-Process $exe | Out-Null } else { Write-Host "  No encuentro $exe : abre Docker Desktop a mano" -ForegroundColor Red }
  for ($i = 1; $i -le 36; $i++) {
    Start-Sleep -Seconds 5
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "  Docker listo ($($i*5) s)" -ForegroundColor Green; return $true }
    Write-Host "  ...esperando Docker ($($i*5) s)"
  }
  return $false
}

Write-Host "PLANTA SIMULADA - MCP Industrial" -ForegroundColor Yellow
Write-Host "Proyecto: $raiz"

if (-not $SoloDocker) {
Paso '1/6 Comprobando Python y archivos'
if (-not (Test-Path $py)) { Write-Host "  NO existe el Python del venv: $py" -ForegroundColor Red; exit 1 }
Write-Host "  Python OK: $py"
if (-not (Test-Path $ml1100)) { Write-Host "  AVISO: no encuentro conector_edge_ml1100.py (nivel no publicara)" -ForegroundColor Yellow } else { Write-Host "  Conector de nivel OK" }

Paso '2/6 Deteniendo lectores de la planta REAL y simulaciones previas (para que no mezclen datos)'
$lanzadores = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'launch_\w+\.ps1' }
$conectores = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'conector_(edge|control)_\w+\.py' }
$simsPrevios = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'simulador\.(temperatura|caudal|nivel|presion)' }
foreach ($p in $simsPrevios) { Write-Host "  cerrando simulador previo PID $($p.ProcessId)"; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
if (-not $lanzadores -and -not $conectores) { Write-Host '  no habia lectores reales corriendo' }
foreach ($p in @($lanzadores) + @($conectores)) {
  if ($p) {
    $nombre = ([regex]::Match($p.CommandLine, '(launch_\w+\.ps1|conector_\w+\.py)')).Value
    Write-Host "  deteniendo PID $($p.ProcessId)  $nombre"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

Paso '2b/6 Revisando que los puertos de los PLC virtuales esten libres'
foreach ($puerto in 502, 1102, 44818, 6341) {
  $duenos = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
  if (-not $duenos) { Write-Host "  puerto $puerto libre"; continue }
  foreach ($id in $duenos) {
    $pr = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    $nombre = if ($pr) { $pr.Name } else { '?' }
    if ($pr -and $pr.Name -like 'python*') {
      Write-Host "  puerto $puerto ocupado por python (PID $id, simulacion vieja): se cierra" -ForegroundColor Yellow
      Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    } else {
      Write-Host "  puerto $puerto ocupado por $nombre (PID $id): NO es nuestro, el PLC virtual de ese puerto puede fallar" -ForegroundColor Red
      if ($pr) { Write-Host "    ruta: $($pr.ExecutablePath)" }
    }
  }
}
Start-Sleep -Seconds 1

Paso '3/6 Iniciando los 4 PLC virtuales'
Ventana 'SIM temperatura  (Twido  Modbus :502)'      '-m simulador.temperatura --host 0.0.0.0'
Ventana 'SIM caudal  (S7-200  :1102)'                '-m simulador.caudal --host 0.0.0.0 --port 1102'   # el 102 lo usa el servicio de Siemens (s7oiehsx64)
Ventana 'SIM nivel  (MicroLogix 1100  ENIP :44818)'  '-m simulador.nivel --host 0.0.0.0'
Ventana 'SIM presion  (cFP-2200  :6341)'             '-m simulador.presion --host 0.0.0.0'
Write-Host '  esperando 4 s a que abran sus puertos...'
Start-Sleep -Seconds 4

Paso '4/6 Iniciando conectores EDGE (lectura) contra 127.0.0.1'
Ventana 'EDGE temperatura a MQTT' "`"$con\conector_edge_twido.py`" --plc 127.0.0.1 --broker $brokerWin --puerto $puertoWin --periodo 1"
$env:CONTROL_CAUDAL_REAL = '1'   # el conector de caudal es unificado (lee y escribe); aqui solo escribe al simulador
Ventana 'EDGE y CONTROL caudal a MQTT' "`"$con\conector_edge_s7200.py`" --plc 127.0.0.1 --puerto-plc 1102 --local-tsap 1000 --remote-tsap 1000 --broker $brokerWin --puerto $puertoWin --periodo 1"
Remove-Item Env:CONTROL_CAUDAL_REAL
if (Test-Path $ml1100) { Ventana 'EDGE nivel a MQTT' "`"$ml1100`" --plc 127.0.0.1 --broker $brokerWin --puerto $puertoWin --periodo 1" }
$env:PYTHONPATH = $shim          # DataSocket falso: el conector de presion habla JSON con el simulador
Ventana 'EDGE presion a MQTT' "`"$con\conector_edge_cfp2200.py`" --cfp 127.0.0.1 --broker $brokerWin --puerto $puertoWin --periodo 1"

Paso '5/6 Iniciando conectores de CONTROL (escriben SOLO al simulador)'
# Las ordenes viajan por el broker Windows (127.0.0.1:1883): no depende de la tarjeta del laboratorio.
# El backend publica ahi en planta simulada (paso 6) y el mirror devuelve los ack al stack Docker.
$env:CONTROL_PRESION_REAL = '1'
Ventana 'CONTROL presion a SIM' "`"$con\conector_control_presion.py`" --cfp 127.0.0.1 --broker $brokerWin --puerto $puertoWin --habilitado-real"
Remove-Item Env:CONTROL_PRESION_REAL
$env:CONTROL_TEMPERATURA_REAL = '1'
Ventana 'CONTROL temperatura a SIM' "`"$con\conector_control_temperatura.py`" --plc 127.0.0.1 --broker $brokerWin --puerto $puertoWin --habilitado-real"
Remove-Item Env:CONTROL_TEMPERATURA_REAL
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Write-Host '  caudal: control incluido en su conector EDGE (unificado)'
Write-Host '  nivel: su control corre en Docker (connector-nivel): se apunta al simulador en el paso 6'

}  # fin de pasos 1-5

Paso '6/6 Backend y control de nivel en MODO_PLANTA=simulado (Docker)'
Set-Content -Path (Join-Path $PSScriptRoot '.modo-planta') -Value 'simulado' -Encoding ascii   # lo usan los bat de reconstruir
Write-Host '  modo guardado en bat\.modo-planta = simulado'
$env:MODO_PLANTA = 'simulado'                    # el SCADA muestra PLANTA SIMULADA y permite mover llaves
$env:PLC_NIVEL_IP = 'host.docker.internal'       # el conector de nivel (Docker) habla con el MicroLogix virtual
$env:CONECTOR_MODO = 'real'; $env:CONTROL_REAL = '1'          # escribe, pero SOLO al simulador
$env:CONTROL_MODO = 'Real'; $env:CONTROL_HABILITADOESCRITURA = 'true'
$env:MQTT_LAB_IP = if (Get-NetIPAddress -IPAddress 192.168.114.100 -ErrorAction SilentlyContinue | Where-Object { (Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue).Status -eq 'Up' }) { '192.168.114.100' } else { '127.0.0.1' }   # broker 1884 sin cable
$env:PRESION_CONTROL_HOST = 'host.docker.internal'; $env:TEMP_CONTROL_HOST = 'host.docker.internal'   # ordenes al broker Windows
if (-not (DockerListo)) {
  Write-Host '  ERROR: Docker no arranco. Abre Docker Desktop y luego ejecuta bat\13-docker-planta-simulada.bat' -ForegroundColor Red
  exit 1
}
Push-Location $raiz
Write-Host '  deteniendo el conector de temperatura REAL de Docker (si existe) para que no tome las ordenes'
docker stop mcpy-connector-temperatura 2>$null | Out-Null
Write-Host '  reiniciando el espejo MQTT (ya no copia ordenes /cmd al broker Docker)'
docker restart mcpy-mirror-tesis 2>$null | Out-Null
Write-Host '  docker compose up -d --build backend connector-nivel frontend  (la primera vez tarda)'
docker compose -f compose.yaml -f compose.override.yaml up -d --build backend connector-nivel frontend
if ($LASTEXITCODE -eq 0) { Write-Host '  backend en MODO_PLANTA=simulado' -ForegroundColor Green } else { Write-Host '  ERROR al levantar Docker: revisa arriba' -ForegroundColor Red }
Pop-Location
foreach ($v in 'MODO_PLANTA','PLC_NIVEL_IP','CONECTOR_MODO','CONTROL_REAL','CONTROL_MODO','CONTROL_HABILITADOESCRITURA','PRESION_CONTROL_HOST','TEMP_CONTROL_HOST','MQTT_LAB_IP') { Remove-Item "Env:$v" -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "LISTO: planta simulada en marcha." -ForegroundColor Green
Write-Host "  - Cada PLC virtual y conector tiene su ventana: ahi ves lo que hace o si falla."
Write-Host "  - Abre el SCADA en modo REAL: dice PLANTA SIMULADA, puedes mover las llaves y todo pasa por MQTT -> backend -> MCP."
Write-Host "  - Para volver a la planta real: bat\11-detener-simulacion.bat"
