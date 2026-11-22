@echo off
chcp 65001 >nul
echo ============================================================
echo  VIGILAR E/S DEL S7-200 DE CAUDAL (solo lectura)
echo  Muestra en vivo que entrada o salida cambia cuando accionas
echo  algo en el tablero: guardamotor, paro de emergencia, pulsadores
echo  (antes corre 18-reiniciar-caudal-real para cargar el conector nuevo)
echo ============================================================
cd /d "%~dp0.."
"%~dp0..\.venv\Scripts\python.exe" -u conectores\vigilar_io.py
pause
