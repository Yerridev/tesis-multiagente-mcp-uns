# Sube el proyecto de tesis a GitHub de forma segura.
#
# Uso (desde Y:\proyects26\tesis):
#   .\subir_github.ps1                       # repo PRIVADO "tesis-multiagente-mcp-uns"
#   .\subir_github.ps1 -Repo otro-nombre
#   .\subir_github.ps1 -Publico              # solo si el laboratorio lo autoriza
#   .\subir_github.ps1 -Mensaje "texto del commit"
#
# Requisitos: Git. Opcional: GitHub CLI (gh) autenticado para crear el repo automaticamente.

param(
    [string]$Repo = "tesis-multiagente-mcp-uns",
    [string]$Mensaje = "Integracion modulo de nivel (MicroLogix 1100), ingestor por equipo y README detallado",
    [switch]$Publico
)

Set-Location $PSScriptRoot

function Fallar($msg) { Write-Host "`n[X] $msg" -ForegroundColor Red; exit 1 }
function Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }

# --- 1. Git disponible y configurado ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fallar "Git no esta instalado: https://git-scm.com/download/win" }
if (-not (git config user.name)) { Fallar "Configura tu identidad: git config --global user.name ""Tu Nombre""" }
if (-not (git config user.email)) { Fallar "Configura tu correo: git config --global user.email ""tu@correo.com""" }

# --- 2. Repositorio local ---
if (-not (Test-Path .git)) {
    git init -b main | Out-Null
    Ok "Repositorio git inicializado (rama main)"
}

git add -A

# --- 3. Verificacion de secretos y archivos que no deben subir ---
$prohibidos = git diff --cached --name-only | Where-Object {
    $_ -match '(^|/)\.env$' -or
    $_ -match 'claude_desktop_config\.json$' -or
    $_ -match '\.(RSS|rss|mwp)$' -or
    $_ -match '(^|/)session-.*\.md$' -or
    $_ -match '(^|/)\.venv/'
}
if ($prohibidos) {
    git reset -q
    Fallar "Abortado: hay archivos sensibles preparados para subir:`n  $($prohibidos -join "`n  ")`nRevisa el .gitignore."
}

$claves = git grep --cached -n -I -E "AIza[0-9A-Za-z_-]{30,}|sk-ant-[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z]{30,}" 2>$null
if ($claves) {
    git reset -q
    Fallar "Abortado: parece haber una clave de API en estos archivos:`n$claves"
}
Ok "Sin secretos detectados"

# --- 4. Commit ---
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nArchivos a subir:" -ForegroundColor Cyan
    git diff --cached --stat | Select-Object -Last 40
    git commit -q -m $Mensaje
    Ok "Commit creado: $Mensaje"
} else {
    Ok "No hay cambios nuevos que confirmar"
}

# --- 5. Remoto y push ---
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        gh auth status 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { Fallar "Ejecuta primero: gh auth login" }
        $vis = if ($Publico) { "--public" } else { "--private" }
        gh repo create $Repo $vis --source . --remote origin --push `
            --description "Tesis USS: arquitectura multiagente de IA + MCP para integrar datos industriales (S7-200, MicroLogix 1100, MQTT/UNS, TimescaleDB)"
        if ($LASTEXITCODE -ne 0) { Fallar "No se pudo crear el repositorio con gh." }
        Ok "Repositorio creado y subido"
        gh repo view --web
        exit 0
    }
    Write-Host "`nNo hay remoto configurado y GitHub CLI (gh) no esta instalado." -ForegroundColor Yellow
    Write-Host "1) Crea un repositorio VACIO (privado) llamado '$Repo' en https://github.com/new"
    Write-Host "2) Ejecuta:"
    Write-Host "     git remote add origin https://github.com/TU_USUARIO/$Repo.git"
    Write-Host "     git push -u origin main"
    exit 0
}

git push -u origin main
if ($LASTEXITCODE -ne 0) { Fallar "Fallo el push. Si el remoto tiene commits previos: git pull --rebase origin main y repite." }
Ok "Subido a $(git remote get-url origin)"
