$ErrorActionPreference = 'Continue'
$py = 'C:\Users\KST\Desktop\INVESTIGACION II\JK\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $dir 'temperatura_edge.log'
while ($true) {
  & $py -u (Join-Path $dir 'conector_edge_twido.py') --plc 192.168.114.10 --broker 192.168.114.100 --puerto 1884 --periodo 1 *>> $log
  Add-Content -LiteralPath $log -Value "[$(Get-Date -Format o)] lector de temperatura detenido; reintento en 5 s"
  Start-Sleep -Seconds 5
}
