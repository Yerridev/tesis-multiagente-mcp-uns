# (Re)crea el arranque automatico de Windows: lectores REALES de los 4 PLC al iniciar sesion.
$raiz = Split-Path -Parent $PSScriptRoot
$con  = Join-Path $raiz 'conectores'
$startup = [Environment]::GetFolderPath('Startup')
$cmd = Join-Path $startup 'MCP-INDUSTRIAL-conectores.cmd'

Write-Host "`n[1/3] Arranque actual: $cmd" -ForegroundColor Cyan
if (Test-Path $cmd) {
  Get-Content $cmd | ForEach-Object { "    $_" }
  Copy-Item $cmd "$cmd.bak" -Force
  Write-Host "  respaldo: $cmd.bak"
} else { Write-Host '  (no existia)' }

Write-Host "`n[2/3] Escribiendo el arranque nuevo (caudal, nivel, presion x2, temperatura)..." -ForegroundColor Cyan
$lanz = 'launch_caudal_edge','launch_nivel_edge','launch_presion_edge','launch_presion_control','launch_temperatura_edge'
$lineas = @('@echo off', 'rem Lectores REALES de la planta (MCP Industrial). Generado por bat\01.2_ArranqueAutomaticoWindows.bat',
            'rem Cada lanzador reinicia su conector si se cae. Logs en tesis-mcp-multiagente-uns\logs\')
foreach ($l in $lanz) { $lineas += "start `"$l`" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$con\$l.ps1`"" }
Set-Content -Path $cmd -Value $lineas -Encoding Default
Get-Content $cmd | ForEach-Object { "    $_" }

Write-Host "`n[3/3] Nota: el control de temperatura va en Docker (mcp-connector-temperatura), no aqui." -ForegroundColor Cyan
Write-Host "Listo. Se aplica la proxima vez que inicies sesion en Windows." -ForegroundColor Green
