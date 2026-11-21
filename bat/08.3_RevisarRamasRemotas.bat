@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================================
echo  08.3 - REVISAR RAMAS REMOTAS (solo lectura: no cambia tu codigo)
echo  1. Baja las ramas de GitHub (origin y Yerri)
echo  2. Lista cada rama con su ultimo commit
echo  3. Muestra que commits y archivos traen respecto a main
echo  Todo queda tambien en logs\ramas-remotas.txt
echo ============================================================
if not exist .git (echo  ALTO: esta carpeta no tiene .git & pause & exit /b 1)
if not exist logs mkdir logs
set "OUT=logs\ramas-remotas.txt"
echo.
echo [1/3] git fetch...
git fetch origin --prune
git fetch yerri --prune
echo.
echo [2/3] Ramas remotas:
powershell -NoProfile -Command "$o = @(); $o += '== RAMAS (' + (Get-Date -Format 'yyyy-MM-dd HH:mm') + ') =='; $o += (git branch -r --sort=-committerdate --format='%%(refname:short) | %%(committerdate:short) | %%(authorname) | %%(subject)'); foreach ($r in (git branch -r --format='%%(refname:short)')) { if ($r -match 'HEAD$' -or $r -eq 'origin/main') { continue }; $o += ''; $o += ('===== ' + $r + ' (commits que NO estan en main) ====='); $o += (git log --oneline --no-merges main..$r); $o += '--- archivos cambiados vs main ---'; $o += (git diff --stat main...$r) }; $o | Set-Content -Encoding UTF8 '%OUT%'; $o"
echo.
echo [3/3] Guardado en %OUT%
echo.
echo LISTO. Avisame y lo reviso.
pause
