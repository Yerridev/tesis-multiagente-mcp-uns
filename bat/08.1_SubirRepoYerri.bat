@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================================
echo  Subir al repo de Yerri: Yerridev/tesis-multiagente-mcp-uns (rama mcp-industrial)
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
echo [2/3] Subiendo a la rama mcp-industrial de Yerri...
git remote get-url yerri >nul 2>&1 || git remote add yerri https://github.com/Yerridev/tesis-multiagente-mcp-uns.git
git push yerri HEAD:refs/heads/mcp-industrial
if errorlevel 1 (echo    ERROR: no se pudo subir. Revisa el mensaje de arriba.) else (echo    OK: subido a yerri/mcp-industrial)
echo.
echo [3/3] Ultimos commits:
git log --oneline -3
echo.
echo LISTO. Puedes cerrar esta ventana.
pause
