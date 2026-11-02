$ErrorActionPreference = 'Continue'
$py   = 'C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe'
$dir  = 'C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\MCP-INDUSTRIAL-NET\conectores'
$log  = 'C:\Users\KST\AppData\Local\Temp\opencode\logs\caudal_control.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$env:CONTROL_CAUDAL_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando conector CONTROL caudal (REAL armado, TSAP 1000)" | Out-File -Append -FilePath $log
while ($true) {
    & $py -u "$dir\conector_control_caudal.py" --plc 192.168.114.7 --local-tsap 1000 --remote-tsap 1000 --broker 127.0.0.1 --habilitado-real *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] conector CONTROL caudal caido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
