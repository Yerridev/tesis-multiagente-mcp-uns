@echo off
cd /d "%~dp0.."
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*conector_edge_cfp2200*' -and $_.Name -like 'python*' } | ForEach-Object { 'matando PID ' + $_.ProcessId; Stop-Process -Id $_.ProcessId -Force }" > reiniciar-edge-presion.log 2>&1
exit
