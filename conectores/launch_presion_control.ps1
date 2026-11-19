$ErrorActionPreference = 'Continue'
# Rutas DENTRO del proyecto: Python propio (.venv) y logs en logs\ (rotan al pasar 20 MB)
$raiz = Split-Path -Parent $PSScriptRoot
$py   = 'C:\Python37-32\python.exe'   # 32 bits: lo exige la DLL de NI-DataSocket
$nids = if ($env:NIDS_DIR) { $env:NIDS_DIR } else { Join-Path $env:USERPROFILE 'NI-DS' }   # carpeta con las DLL de NI (por defecto %USERPROFILE%\NI-DS)
$dir  = Join-Path $nids 'conectores'   # conectores de presion junto a las DLL de NI
$log  = Join-Path $raiz 'logs\presion_control.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Rotar { if ((Test-Path $log) -and (Get-Item $log).Length -gt 20MB) { Move-Item -Force $log "$log.1" } }
if (-not (Test-Path $py)) { "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] FALTA $py (corre bat\00-instalar-python.bat)" | Out-File -Append -FilePath $log; exit 1 }
# Conector CONTROL de presion (cFP-2200): escribe solo INICIO_PC / SALIR_PC.
$env:CONTROL_PRESION_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando CONTROL presion en el HOST (REAL armado)" | Out-File -Append -FilePath $log
while ($true) {
    Rotar
    & $py -u "$dir\conector_control_presion.py" --cfp 192.168.114.8 --broker 192.168.114.100 --puerto 1884 --habilitado-real *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] CONTROL presion detenido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
