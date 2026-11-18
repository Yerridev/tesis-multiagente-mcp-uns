@echo off
rem Auxiliar: comprueba que Docker Desktop este corriendo; si no, lo abre y espera (max. 3 min).
docker info >nul 2>&1 && exit /b 0
echo Docker Desktop no esta corriendo: lo abro y espero (hasta 3 min)...
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
for /l %%i in (1,1,36) do (
  timeout /t 5 /nobreak >nul
  docker info >nul 2>&1 && (echo   Docker listo & exit /b 0)
  echo   ...esperando Docker
)
echo   Docker no arranco: abrelo a mano y vuelve a correr este bat
exit /b 1
