Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'launch_presion_(edge|control)\.ps1|conector_edge_cfp2200|conector_control_presion' } | ForEach-Object { "deteniendo $($_.ProcessId) $($_.Name)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 2
foreach ($n in 'launch_presion_edge.ps1','launch_presion_control.ps1') {
  Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"C:\Users\KST\NI-DS\conectores\$n`"" -WindowStyle Hidden; "arrancado $n" }
