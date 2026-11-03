@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*conector_control_presion*' -and $_.Name -like 'python*' } | ForEach-Object { 'matando PID ' + $_.ProcessId; Stop-Process -Id $_.ProcessId -Force }; $p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*launch_presion_control*' }; if (-not $p) { 'lanzador no estaba corriendo: lo arranco'; Start-Process powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File C:\Users\KST\NI-DS\conectores\launch_presion_control.ps1' -WindowStyle Hidden } else { 'lanzador activo: reinicia solo en 5 s' }" > reiniciar-control-presion.log 2>&1
exit
