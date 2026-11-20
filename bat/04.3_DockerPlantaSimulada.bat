@echo off
chcp 65001 >nul
echo ============================================================
echo  SOLO DOCKER en planta simulada (paso 6 de simular-planta)
echo  Usalo si Docker Desktop estaba cerrado: no reinicia los
echo  simuladores ni los conectores (los tanques no se vacian)
echo ============================================================
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0simular-planta.ps1" -SoloDocker
echo.
echo LISTO. Revisa arriba lo que hizo. Puedes cerrar esta ventana.
pause
