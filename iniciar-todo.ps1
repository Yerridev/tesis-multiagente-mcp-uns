param([switch]$SinLectores)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:CONECTOR_MODO = 'dry-run'
docker compose --profile core --profile simulation --profile monitoring --profile edge -f compose.yaml -f compose.override.yaml up -d --build --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose no pudo iniciar el stack.' }

if (-not $SinLectores) {
    foreach ($nombre in @('presion', 'temperatura')) {
        $script = Join-Path $PSScriptRoot "conectores\launch_${nombre}_edge.ps1"
        $activo = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -like "*$script*" }
        if (-not $activo) {
            Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $script + '"') -WindowStyle Hidden
        }
    }
}

Write-Host 'Stack iniciado desde:' $PSScriptRoot
Write-Host 'Interfaz: http://localhost:8080'
Write-Host 'Estado API: http://127.0.0.1:5295/health/ready'
