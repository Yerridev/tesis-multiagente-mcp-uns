$ErrorActionPreference = 'Continue'
# Rutas DENTRO del proyecto: Python propio (.venv) y logs en logs\ (rotan al pasar 20 MB)
$raiz = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $raiz '.venv\Scripts\python.exe'
$dir  = $PSScriptRoot
$log  = Join-Path $raiz 'logs\temperatura_edge.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Rotar { if ((Test-Path $log) -and (Get-Item $log).Length -gt 20MB) { Move-Item -Force $log "$log.1" } }
if (-not (Test-Path $py)) { "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] FALTA $py (corre bat\01.0_InstalarPython.bat)" | Out-File -Append -FilePath $log; exit 1 }
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando lector de temperatura (Twido)" | Out-File -Append -FilePath $log
while ($true) {
    Rotar
    & $py -u "$dir\conector_edge_twido.py" --plc 192.168.114.10 --broker 192.168.114.100 --puerto 1884 --periodo 1 *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] lector de temperatura detenido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
