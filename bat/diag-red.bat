@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\conectores\diag_red.ps1" > diag-red.log 2>&1
exit
