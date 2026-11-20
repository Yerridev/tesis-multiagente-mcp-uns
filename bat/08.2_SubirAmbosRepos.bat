@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================================
echo  08.2 - SUBIR A AMBOS REPOS (version Python: tesis-mcp-multiagente-uns)
echo   - Nuestro : bvasquezkeysije/tesis-mcp-multiagent-uns   (main)
echo   - Yerri   : Yerridev/tesis-multiagente-mcp-uns        (mcp-industrial)
echo  Un solo commit y se sube a los dos (sin force).
echo ============================================================
echo.
if not exist .git (
  echo  ALTO: esta carpeta no tiene repo propio ^(.git^).
  echo  Si sigues, git usaria el repo de arriba ^(INVESTIGACION-I^) y subiria toda la carpeta JK.
  pause & exit /b 1
)
echo  Carpeta: %CD%
git remote get-url yerri >nul 2>&1 || git remote add yerri https://github.com/Yerridev/tesis-multiagente-mcp-uns.git
echo.
echo [1/4] Preparando el commit (el .gitignore excluye .env, .venv, logs, node_modules)...
git add -A
git diff --cached --name-only | findstr /r /i "\.env$ \.env\." | findstr /v /i "example" && (echo    ERROR: se iba a subir un .env. Cancelo. & git reset & pause & exit /b 1)
git diff --cached --shortstat
if exist .commitmsg.txt (
  git commit -F .commitmsg.txt
  del .commitmsg.txt
) else (
  git diff --cached --quiet && echo    No hay cambios nuevos para commitear. || git commit -m "Actualizacion %date% %time%"
)
echo.
echo [2/4] Subiendo a NUESTRO repo (origin main)...
git push origin HEAD:main
if errorlevel 1 (echo    ERROR: no se pudo subir a origin. Revisa el mensaje de arriba.) else (echo    OK: subido a origin/main)
echo.
echo [3/4] Subiendo al repo de YERRI (mcp-industrial)...
git push yerri HEAD:refs/heads/mcp-industrial
if errorlevel 1 (echo    ERROR: no se pudo subir a Yerri. Revisa el mensaje de arriba.) else (echo    OK: subido a yerri/mcp-industrial)
echo.
echo [4/4] Ultimos commits:
git log --oneline -3
echo.
echo LISTO. Puedes cerrar esta ventana.
pause
