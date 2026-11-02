$ErrorActionPreference = 'Continue'
# Conector EDGE de presion (cFP-2200) en el HOST, via DataSocket/PSP (nids 4.9 por usuario).
# Publica en el broker del stack Docker: 192.168.114.70:1884
$py  = 'C:\Python37-32\python.exe'
$dir = 'C:\Users\KST\NI-DS\conectores'
$log = 'C:\Users\KST\NI-DS\logs\presion_edge.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando EDGE presion en el HOST (DataSocket psp://)" | Out-File -Append -FilePath $log
while ($true) {
    & $py -u "$dir\conector_edge_cfp2200.py" --cfp 192.168.114.8 --broker 192.168.114.70 --puerto 1884 --periodo 1 *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] EDGE presion caido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
