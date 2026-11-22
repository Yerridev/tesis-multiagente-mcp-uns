$ErrorActionPreference = 'Continue'
# Rutas DENTRO del proyecto: Python propio (.venv) y logs en logs\ (rotan al pasar 20 MB)
$raiz = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $raiz '.venv\Scripts\python.exe'
$dir  = $PSScriptRoot
$log  = Join-Path $raiz 'logs\caudal_edge.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Rotar { if ((Test-Path $log) -and (Get-Item $log).Length -gt 20MB) { Move-Item -Force $log "$log.1" } }
if (-not (Test-Path $py)) { "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] FALTA $py (corre bat\00-instalar-python.bat)" | Out-File -Append -FilePath $log; exit 1 }
# Conector unificado: lee (telemetria) y escribe (control) en la MISMA sesion S7
# (el CP243-1 del S7-200 admite una sola sesion). Gate real: CONTROL_CAUDAL_REAL=1 + --habilitado-real + M0.3=PC + REMOTO.
$env:CONTROL_CAUDAL_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando conector EDGE caudal (origen .70, TSAP 1000, control real con validaciones)" | Out-File -Append -FilePath $log
while ($true) {
    Rotar
    & $py -u "$dir\conector_edge_s7200.py" --plc 192.168.114.7 --source-ip 192.168.114.70 --local-tsap 1000 --remote-tsap 1000 --broker 127.0.0.1 --puerto 1883 --periodo 1 *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] conector EDGE caudal detenido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
