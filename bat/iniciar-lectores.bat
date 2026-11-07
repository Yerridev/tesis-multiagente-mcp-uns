@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\conectores\iniciar_lectores.ps1" > iniciar-lectores.log 2>&1
exit
