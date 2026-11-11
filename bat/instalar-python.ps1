# Crea el Python propio del proyecto (.venv) e instala sus librerias (requirements.txt).
$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $raiz '.venv'
$py   = Join-Path $venv 'Scripts\python.exe'

function Version($exe, [string[]]$pre = @()) {
  try { $v = & $exe @pre -c "import sys,struct;print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8))" 2>$null; return $v } catch { return $null }
}

Write-Host "`n[1/4] Buscando Python 3.10 o superior (64 bits) en la PC..." -ForegroundColor Cyan
$base = $null; $basePre = @()
foreach ($c in @(@('py', @('-3.12')), @('py', @('-3.11')), @('py', @('-3.13')), @('py', @('-3.10')), @('python', @()), @('python3', @()))) {
  $v = Version $c[0] $c[1]
  if ($v -match '^3\.(\d+) 64' -and [int]$Matches[1] -ge 10) { $base = $c[0]; $basePre = $c[1]; Write-Host "  encontrado: $($c[0]) $($c[1] -join ' ')  -> Python $v bits" -ForegroundColor Green; break }
  elseif ($v) { Write-Host "  descartado: $($c[0]) $($c[1] -join ' ') -> Python $v bits (necesito 3.10+ de 64 bits)" }
}
if (-not $base) {
  Write-Host '  No hay Python 3.10+ de 64 bits instalado.' -ForegroundColor Yellow
  $r = Read-Host '  Instalar Python 3.12 ahora con winget? (S/N)'
  if ($r -match '^[sS]') {
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    if (Version 'py' @('-3.12')) { $base = 'py'; $basePre = @('-3.12') }
  }
  if (-not $base) { Write-Host '  Instala Python 3.12 (python.org, marca "Add to PATH") y vuelve a correr este bat.' -ForegroundColor Red; exit 1 }
}

Write-Host "`n[2/4] Creando el entorno del proyecto en .venv ..." -ForegroundColor Cyan
if (Test-Path $py) { Write-Host '  ya existia: se reutiliza (solo se actualizan librerias)' }
else { & $base @basePre -m venv $venv; if (-not (Test-Path $py)) { Write-Host '  ERROR creando .venv' -ForegroundColor Red; exit 1 } ; Write-Host '  creado' -ForegroundColor Green }

Write-Host "`n[3/4] Instalando librerias (requirements.txt)..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip --disable-pip-version-check -q
& $py -m pip install -r (Join-Path $raiz 'requirements.txt') --disable-pip-version-check

Write-Host "`n[4/4] Verificando..." -ForegroundColor Cyan
& $py -c "import paho.mqtt, snap7, pycomm3, pymodbus, httpx, mcp; import sys; print('  OK  Python', sys.version.split()[0], '·', sys.executable)"
if ($LASTEXITCODE -ne 0) { Write-Host '  Falta alguna libreria (revisa los errores de arriba)' -ForegroundColor Red; exit 1 }
Write-Host "`nListo. Todos los bats y lectores usan ahora: $py" -ForegroundColor Green
