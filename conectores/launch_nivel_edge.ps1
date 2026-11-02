$ErrorActionPreference = 'Continue'
$py   = 'C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe'
$dir  = 'C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador'
$log  = 'C:\Users\KST\AppData\Local\Temp\opencode\logs\nivel_edge.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] arrancando conector EDGE nivel (MicroLogix 1100)" | Out-File -Append -FilePath $log
while ($true) {
    & $py -u "$dir\conector_edge_ml1100.py" --plc 192.168.114.9 --broker 127.0.0.1 --puerto 1883 --periodo 1 *>> $log
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] conector EDGE nivel caido; reinicio en 5 s" | Out-File -Append -FilePath $log
    Start-Sleep -Seconds 5
}
