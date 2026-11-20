$ErrorActionPreference = 'Continue'
# Rutas DENTRO del proyecto: Python propio (.venv) y logs en logs\ (rotan al pasar 20 MB)
$raiz = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $raiz '.venv\Scripts\python.exe'
$dir  = $PSScriptRoot
$log  = Join-Path $raiz 'logs\caudal_control.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Rotar { if ((Test-Path $log) -and (Get-Item $log).Length -gt 20MB) { Move-Item -Force $log "$log.1" } }
if (-not (Test-Path $py)) { "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] FALTA $py (corre bat\01.0_InstalarPython.bat)" | Out-File -Append -FilePath $log; exit 1 }
# NO usar junto con launch_caudal_edge.ps1: el CP243-1 admite una sola sesion S7
$env:CONTROL_CAUDAL_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando conector CONTROL caudal (REAL armado, TSAP 1000)" | Out-File -Append -FilePath $log
while ($true) {
    Rotar
    & $py -u "$dir\conector_control_caudal.py" --plc 192.168.114.7 --local-tsap 1000 --remote-tsap 1000 --broker 127.0.0.1 --habilitado-real *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] conector CONTROL caudal detenido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
