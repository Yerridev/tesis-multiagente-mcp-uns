$ErrorActionPreference = 'Continue'
# Rutas DENTRO del proyecto: Python propio (.venv) y logs en logs\ (rotan al pasar 20 MB)
$raiz = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $raiz '.venv\Scripts\python.exe'
$dir  = $PSScriptRoot
$log  = Join-Path $raiz 'logs\temperatura_control.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Rotar { if ((Test-Path $log) -and (Get-Item $log).Length -gt 20MB) { Move-Item -Force $log "$log.1" } }
if (-not (Test-Path $py)) { "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] FALTA $py (corre bat\00-instalar-python.bat)" | Out-File -Append -FilePath $log; exit 1 }
# Control REAL protegido del MCT-09: solo %M30 y %MW100. Cerrar TwidoSuite antes.
# NO usar junto con el contenedor mcp-connector-temperatura (mismo cliente MQTT).
$env:CONTROL_TEMPERATURA_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando Control temperatura armado (M30/MW100 solamente)" | Out-File -Append -FilePath $log
while ($true) {
    Rotar
    & $py -u "$dir\conector_control_temperatura.py" --plc 192.168.114.10 --broker 192.168.114.100 --puerto 1884 --habilitado-real *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Conector temperatura detenido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
