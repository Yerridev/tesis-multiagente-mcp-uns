$ErrorActionPreference = 'Continue'
# Conector CONTROL de presion (cFP-2200) en el HOST, via DataSocket/PSP.
# Escribe solo INICIO_PC / SALIR_PC (mando del supervisor del cFP-2200).
$py  = 'C:\Python37-32\python.exe'
$dir = 'C:\Users\KST\NI-DS\conectores'
$log = 'C:\Users\KST\NI-DS\logs\presion_control.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$env:CONTROL_PRESION_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando CONTROL presion en el HOST (REAL armado)" | Out-File -Append -FilePath $log
while ($true) {
    & $py -u "$dir\conector_control_presion.py" --cfp 192.168.114.8 --broker 192.168.114.70 --puerto 1884 --habilitado-real *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] CONTROL presion caido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
