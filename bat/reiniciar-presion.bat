@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\conectores\reiniciar_presion_nids.ps1" > reiniciar-presion.log 2>&1
exit
