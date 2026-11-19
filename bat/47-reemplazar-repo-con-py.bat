@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================================
echo  47 - REEMPLAZAR EL REPO (C#) POR ESTA VERSION PYTHON
echo   - Tu repo  : bvasquezkeysije/tesis-mcp-multiagent-uns  (main)
echo   - Yerri    : Yerridev/tesis-multiagente-mcp-uns  (mcp-industrial)
echo  Se agrega UN commit encima del historial (sin force):
echo  la version C# queda guardada en los commits anteriores.
echo  ANTES: corre los bats 22 y 23 de la carpeta ORIGINAL.
echo ============================================================
echo.
echo Cierra esta ventana para CANCELAR, o
pause
echo.
echo [1/6] Preparando git en esta carpeta...
if not exist .git (
  git init -b main
  git remote add origin https://github.com/bvasquezkeysije/tesis-mcp-multiagent-uns.git
)
git remote get-url yerri >nul 2>&1 || git remote add yerri https://github.com/Yerridev/tesis-multiagente-mcp-uns.git
git remote -v
echo.
echo [2/6] Bajando el historial de tu repo (origin/main)...
git fetch origin main || (echo    ERROR al bajar origin/main & pause & exit /b 1)
git reset --mixed origin/main
echo.
echo [3/6] Preparando archivos (el .gitignore excluye .env, .venv, logs, node_modules)...
git add -A
git diff --cached --name-only | findstr /r /i "\.env$ \.env\." | findstr /v /i "example" && (echo    ERROR: se iba a subir un .env. Cancelo. & git reset & pause & exit /b 1)
echo    resumen de cambios:
git diff --cached --shortstat
echo.
echo [4/6] Commit...
if exist .commitmsg.txt (git commit -F .commitmsg.txt) else (git commit -m "Migracion del backend a Python (FastAPI)")
echo.
echo [5/6] Subiendo a TU repo (origin main)...
git push origin HEAD:main
if errorlevel 1 (echo    ERROR: no se pudo subir a origin. Pasame el mensaje. & pause & exit /b 1)
echo    OK: subido a origin/main
echo.
echo [6/6] Subiendo al repo de YERRI (mcp-industrial)...
git push yerri HEAD:refs/heads/mcp-industrial
if errorlevel 1 (echo    ERROR: no se pudo subir a Yerri. Pasame el mensaje.) else (echo    OK: subido a yerri/mcp-industrial)
echo.
git log --oneline -3
if exist .commitmsg.txt del .commitmsg.txt
echo.
echo LISTO.
pause
