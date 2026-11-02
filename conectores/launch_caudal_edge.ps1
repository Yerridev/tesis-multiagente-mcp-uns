$ErrorActionPreference = 'Continue'
$py   = 'C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe'
$dir  = 'C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador'
$log  = 'C:\Users\KST\AppData\Local\Temp\opencode\logs\caudal_edge.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
# Conector unificado: lee (telemetria) y escribe (control) en la MISMA sesion S7
# (el CP243-1 del S7-200 admite una sola sesion). El gate real vive en el propio
# conector: CONTROL_CAUDAL_REAL=1 + --habilitado-real + M0.3=PC + selector REMOTO.
$env:CONTROL_CAUDAL_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando conector EDGE+CONTROL caudal (TSAP 1000, CONTROL_CAUDAL_REAL=1)" | Out-File -Append -FilePath $log
while ($true) {
    & $py -u "$dir\conector_edge_s7200.py" --plc 192.168.114.7 --local-tsap 1000 --remote-tsap 1000 --broker 127.0.0.1 --puerto 1883 --periodo 1 *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] conector EDGE caudal caido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
