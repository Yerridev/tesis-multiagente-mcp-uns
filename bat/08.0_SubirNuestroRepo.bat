@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================================
echo  Subir a NUESTRO repo: bvasquezkeysije/tesis-mcp-multiagent-uns (main)
echo ============================================================
echo.
if not exist .git (
  echo  ALTO: esta carpeta todavia no tiene repo propio.
  echo  Si sigues, git usaria el repo de arriba ^(INVESTIGACION-I^) y subiria toda la carpeta JK.
  echo  Debe correrse desde tesis-mcp-multiagente-uns ^(con su carpeta .git^).
  pause & exit /b 1
)
echo [1/3] Preparando el commit...
git add -A
if exist .commitmsg.txt (
  git commit -F .commitmsg.txt
  del .commitmsg.txt
) else (
  git diff --cached --quiet && echo    No hay cambios nuevos para commitear. || git commit -m "Actualizacion %date% %time%"
)
echo.
echo [2/3] Subiendo a origin main...
git push origin HEAD:main
if errorlevel 1 (echo    ERROR: no se pudo subir. Revisa el mensaje de arriba.) else (echo    OK: subido a origin/main)
echo.
echo [3/3] Ultimos commits:
git log --oneline -3
echo.
echo LISTO. Puedes cerrar esta ventana.
pause
