@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'caudal_edge|s7200' -and $_.ProcessId -ne $PID } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 3 >nul
if not defined NIDS_DIR set "NIDS_DIR=%USERPROFILE%\NI-DS"
start "" /min powershell -ExecutionPolicy Bypass -File "%NIDS_DIR%\conectores\launch_caudal_edge.ps1"
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
