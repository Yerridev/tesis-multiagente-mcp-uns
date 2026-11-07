@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'caudal_edge|s7200' -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 3 >nul
start "" /min powershell -ExecutionPolicy Bypass -File "C:\Users\KST\NI-DS\conectores\launch_caudal_edge.ps1"
