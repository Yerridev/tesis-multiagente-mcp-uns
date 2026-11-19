$ErrorActionPreference = 'Continue'
# Rutas DENTRO del proyecto: Python propio (.venv) y logs en logs\ (rotan al pasar 20 MB)
$raiz = Split-Path -Parent $PSScriptRoot
$py   = 'C:\Python37-32\python.exe'   # 32 bits: lo exige la DLL de NI-DataSocket
$dir  = 'C:\Users\KST\NI-DS\conectores'   # conectores de presion junto a las DLL de NI
$log  = Join-Path $raiz 'logs\presion_edge.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Rotar { if ((Test-Path $log) -and (Get-Item $log).Length -gt 20MB) { Move-Item -Force $log "$log.1" } }
if (-not (Test-Path $py)) { "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] FALTA $py (corre bat\00-instalar-python.bat)" | Out-File -Append -FilePath $log; exit 1 }
# Conector EDGE de presion (cFP-2200) via DataSocket/PSP. Publica en el broker Docker 192.168.114.100:1884
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando EDGE presion en el HOST (DataSocket psp://)" | Out-File -Append -FilePath $log
while ($true) {
    Rotar
    & $py -u "$dir\conector_edge_cfp2200.py" --cfp 192.168.114.8 --broker 192.168.114.100 --puerto 1884 --periodo 1 *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EDGE presion detenido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
