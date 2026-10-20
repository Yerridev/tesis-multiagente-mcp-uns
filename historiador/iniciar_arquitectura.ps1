# Arranque de la arquitectura de tesis (solo lectura): PLC -> conector -> MQTT/UNS -> TimescaleDB/Grafana -> MCP
# Uso: doble clic en INICIAR_TODO.bat (o: powershell -ExecutionPolicy Bypass -File iniciar_arquitectura.ps1)
# Todo queda registrado en historiador\logs\arranque.log
$ErrorActionPreference = "Continue"
$Raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Raiz
$Logs = Join-Path $Raiz "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Log = Join-Path $Logs "arranque.log"
"" | Set-Content -Encoding UTF8 $Log

function Paso($t) { $l = "`n===== $t ====="; Write-Host $l -ForegroundColor Cyan; Add-Content -Encoding UTF8 $Log $l }
function Info($t) { Write-Host $t; Add-Content -Encoding UTF8 $Log $t }
function Ok($t)   { Write-Host "[OK] $t" -ForegroundColor Green; Add-Content -Encoding UTF8 $Log "[OK] $t" }
function Mal($t)  { Write-Host "[ERROR] $t" -ForegroundColor Red; Add-Content -Encoding UTF8 $Log "[ERROR] $t" }
function Aviso($t){ Write-Host "[AVISO] $t" -ForegroundColor Yellow; Add-Content -Encoding UTF8 $Log "[AVISO] $t" }
function Puerto($h, $p) { try { $c = New-Object Net.Sockets.TcpClient; $r = $c.BeginConnect($h, $p, $null, $null); $ok = $r.AsyncWaitHandle.WaitOne(2000); if ($ok) { $c.EndConnect($r) }; $c.Close(); return $ok } catch { return $false } }

Info ("Inicio: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "  carpeta: $Raiz")

# ---------------------------------------------------------------- 1. .env
Paso "1. Configuracion (.env)"
$Cfg = @{}
if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match "^\s*[A-Z_]+=" } | ForEach-Object { $k, $v = $_ -split "=", 2; $Cfg[$k.Trim()] = $v.Trim() }
    Ok (".env encontrado (" + $Cfg.Count + " claves)")
} else { Mal "No existe .env (copia .env.example a .env)"; exit 1 }
$DbUser = $Cfg["DB_USER"]; $DbName = $Cfg["DB_NAME"]; $LectorPwd = $Cfg["MCP_READER_PASSWORD"]
if (-not $Cfg.ContainsKey("LLM_PROVEEDOR")) {
    Add-Content -Encoding UTF8 ".env" "`nLLM_PROVEEDOR=gemini`nGEMINI_MODEL=gemini-3.8-flash"
    $Cfg["LLM_PROVEEDOR"] = "gemini"
    Info "Se agrego LLM_PROVEEDOR=gemini al .env"
}
if (-not $Cfg.ContainsKey("GEMINI_API_KEY")) {
    Add-Content -Encoding UTF8 ".env" "GEMINI_API_KEY="
    $Cfg["GEMINI_API_KEY"] = ""
}
$Prov = $Cfg["LLM_PROVEEDOR"]
$ClaveLlm = if ($Prov -eq "anthropic") { "ANTHROPIC_API_KEY" } elseif ($Prov -eq "gemini") { "GEMINI_API_KEY" } else { "LLM_API_KEY" }
if ($Cfg[$ClaveLlm]) { Ok "Agente del lienzo: proveedor $Prov, clave $ClaveLlm configurada" }
else { Aviso "Agente del lienzo: proveedor $Prov sin clave ($ClaveLlm vacia en el .env); el lienzo funciona sin chat" }

# ---------------------------------------------------------------- 2. Red y PLC
Paso "2. Red del laboratorio y PLC"
$ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty IPAddress)
Info ("IPs de esta laptop: " + ($ips -join ", "))
if ($ips -contains "192.168.114.10") { Ok "La laptop tiene 192.168.114.10 (cliente autorizado del enlace 1)" }
else { Aviso "La laptop NO tiene 192.168.114.10: el enlace 1 del CP243-1 rechazara la conexion" }
if (Test-Connection -ComputerName 192.168.114.7 -Count 2 -Quiet) { Ok "PLC 192.168.114.7 responde a ping" } else { Mal "PLC 192.168.114.7 no responde a ping" }
if (Puerto "192.168.114.7" 102) { Ok "Puerto S7 (TCP 102) del PLC abierto" } else { Mal "Puerto TCP 102 del PLC no responde" }

# ---------------------------------------------------------------- 3. Mosquitto
Paso "3. Broker MQTT (Mosquitto)"
if (-not (Puerto "127.0.0.1" 1883)) {
    $svc = Get-Service -Name mosquitto -ErrorAction SilentlyContinue
    if ($svc) { Info "Servicio mosquitto: $($svc.Status). Intentando iniciarlo..."; try { Start-Service mosquitto -ErrorAction Stop } catch { Aviso "No se pudo iniciar el servicio (requiere administrador): $_" } ; Start-Sleep 3 }
}
if (Puerto "127.0.0.1" 1883) { Ok "Mosquitto escuchando en 1883" } else { Mal "Mosquitto no escucha en 1883. Inicia el servicio 'Mosquitto Broker' como administrador." }
$conf = "C:\Program Files\mosquitto\mosquitto.conf"
if (Test-Path $conf) {
    $c = Get-Content $conf | Where-Object { $_ -notmatch "^\s*#" -and $_.Trim() -ne "" }
    Info ("mosquitto.conf (lineas activas): " + ($c -join " | "))
    if (-not ($c -match "listener\s+1883")) { Aviso "mosquitto.conf no tiene 'listener 1883 0.0.0.0': Docker (ingestor) no podra conectarse" }
}

# ---------------------------------------------------------------- 4. Docker
Paso "4. Docker: TimescaleDB, ingestor y Grafana"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Aviso "Docker no responde. Abriendo Docker Desktop y esperando hasta 2 min..."
    $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) { Start-Process $dd }
    for ($i = 0; $i -lt 24; $i++) { Start-Sleep 5; docker info *> $null; if ($LASTEXITCODE -eq 0) { break } }
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { Mal "Docker sigue sin responder. Abre Docker Desktop y vuelve a ejecutar."; exit 1 }
Ok "Docker responde"
docker compose up -d --build 2>&1 | ForEach-Object { Info "  $_" }
Info "Esperando a TimescaleDB..."
for ($i = 0; $i -lt 30; $i++) { docker exec uns-timescaledb pg_isready -U $DbUser -d $DbName *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 2 }
if ($LASTEXITCODE -eq 0) { Ok "TimescaleDB lista" } else { Mal "TimescaleDB no responde" }
docker compose ps 2>&1 | ForEach-Object { Info "  $_" }

# ---------------------------------------------------------------- 5. Migracion v3.2 (una sola vez)
Paso "5. Migracion de nombres v3.2"
$marca = Join-Path $Raiz "db\.migracion_v32_aplicada"
if (Test-Path $marca) { Ok "Ya aplicada anteriormente" }
else {
    Get-Content -Raw "db\04_migracion_v32.sql" | docker exec -i uns-timescaledb psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1 2>&1 | ForEach-Object { Info "  $_" }
    if ($LASTEXITCODE -eq 0) { Get-Date | Set-Content $marca; Ok "Migracion aplicada" } else { Mal "La migracion fallo (ver lineas anteriores)" }
}

# ---------------------------------------------------------------- 6. Python
Paso "6. Entornos de Python"
$Venv = Join-Path $Raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $Venv)) { Info "Creando .venv..."; python -m venv .venv }
& $Venv -m pip install -q --disable-pip-version-check -r mcp_servidor\requirements.txt 2>&1 | ForEach-Object { Info "  $_" }
# Para el conector se prefiere el Python que ya leia el PLC (tiene snap7 probado); si no, se instala en el venv.
$PyConector = $null
foreach ($cand in @("python", "py")) {
    $exe = (Get-Command $cand -ErrorAction SilentlyContinue).Source
    if ($exe) { & $exe -c "import snap7, paho.mqtt" *> $null; if ($LASTEXITCODE -eq 0) { $PyConector = $exe; break } }
}
if (-not $PyConector) {
    Info "Instalando python-snap7 y paho-mqtt en el .venv..."
    & $Venv -m pip install -q --disable-pip-version-check python-snap7 paho-mqtt 2>&1 | ForEach-Object { Info "  $_" }
    $PyConector = $Venv
}
$verSnap7 = & $PyConector -c "import importlib.metadata as m; print(m.version('python-snap7'))" 2>&1
Ok "Python del conector: $PyConector (python-snap7 $verSnap7)"
& $Venv -c "import mcp, psycopg; print('mcp', __import__('importlib.metadata').metadata.version('mcp'))" 2>&1 | ForEach-Object { Info "  $_" }

# ---------------------------------------------------------------- 7. Conector edge
Paso "7. Conector edge PLC -> MQTT"
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*conector_edge_s7200*" } |
    ForEach-Object { Info "Deteniendo conector anterior (PID $($_.ProcessId))"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$LogCon = Join-Path $Logs "conector.log"
$cmd = "`$host.UI.RawUI.WindowTitle='CONECTOR EDGE S7-200 (Ctrl+C para detener)'; Set-Location '$Raiz'; `$env:PYTHONUNBUFFERED='1'; & '$PyConector' conector_edge_s7200.py 2>&1 | Tee-Object -FilePath '$LogCon'"
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $cmd
Info "Conector lanzado en otra ventana. Esperando 20 s de datos..."
Start-Sleep 20
if (Test-Path $LogCon) { Get-Content $LogCon -Tail 30 | ForEach-Object { Info "  $_" } }

# ---------------------------------------------------------------- 8. Datos llegando a la base
Paso "8. Datos en el historiador"
$sql = "SELECT variable, round(valor::numeric,3) AS valor, unidad, to_char(time AT TIME ZONE 'America/Lima','HH24:MI:SS') AS hora FROM (SELECT DISTINCT ON (variable) * FROM mediciones WHERE fuente='uns' AND time > now() - interval '5 minutes' ORDER BY variable, time DESC) t ORDER BY variable;"
docker exec uns-timescaledb psql -U $DbUser -d $DbName -c $sql 2>&1 | ForEach-Object { Info "  $_" }
docker logs --tail 8 uns-ingestor 2>&1 | ForEach-Object { Info "  ingestor> $_" }

# ---------------------------------------------------------------- 9. Servidor MCP
Paso "9. Servidor MCP (prueba de las 7 herramientas)"
$env:MCP_DSN = "postgresql://mcp_lector:$LectorPwd@localhost:5432/$DbName"
$LogMcp = Join-Path $Logs "mcp_probar.log"
& $Venv mcp_servidor\servidor_mcp.py --probar 2>&1 | ForEach-Object { "$_" } | Out-File -Encoding utf8 $LogMcp
Get-Content $LogMcp | Select-String -Pattern "=====|ERROR|estado|evaluacion|datos_en_vivo|modo" | ForEach-Object { Info "  $($_.Line.Trim())" }
Ok "Resultado completo en logs\mcp_probar.log"

# ---------------------------------------------------------------- 10. Claude Desktop
Paso "10. Configuracion de Claude Desktop"
$cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
try {
    if (Test-Path $cfgPath) { Copy-Item $cfgPath "$cfgPath.respaldo_$(Get-Date -Format yyyyMMdd_HHmmss)"; $cfg = Get-Content -Raw $cfgPath | ConvertFrom-Json }
    else { New-Item -ItemType Directory -Force -Path (Split-Path $cfgPath) | Out-Null; $cfg = New-Object PSObject }
    if (-not $cfg.PSObject.Properties["mcpServers"]) { $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue (New-Object PSObject) }
    $srv = [PSCustomObject]@{ command = $Venv; args = @((Join-Path $Raiz "mcp_servidor\servidor_mcp.py")); env = [PSCustomObject]@{ MCP_DSN = $env:MCP_DSN } }
    if ($cfg.mcpServers.PSObject.Properties["caudal-mcc09"]) { $cfg.mcpServers."caudal-mcc09" = $srv } else { $cfg.mcpServers | Add-Member -NotePropertyName "caudal-mcc09" -NotePropertyValue $srv }
    $json = $cfg | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($cfgPath, $json, (New-Object Text.UTF8Encoding($false)))
    Ok "Servidor 'caudal-mcc09' registrado en $cfgPath (se activa al reiniciar Claude Desktop)"
} catch { Mal "No se pudo escribir la configuracion de Claude Desktop: $_" }

# ---------------------------------------------------------------- 11. Lienzo vivo y Grafana
Paso "11. Lienzo vivo y Grafana"
for ($i = 0; $i -lt 20; $i++) { if (Puerto "127.0.0.1" 8765) { break }; Start-Sleep 2 }
if (Puerto "127.0.0.1" 8765) {
    try { $s = Invoke-RestMethod "http://127.0.0.1:8765/api/salud" -TimeoutSec 5; Info ("  salud del lienzo: db=" + $s.db + " mqtt=" + $s.mqtt + " agente=" + $s.agente + " proveedor=" + $s.proveedor + " modelo=" + $s.modelo) } catch { Aviso "El lienzo responde pero /api/salud fallo: $_" }
    Ok "Lienzo vivo en http://localhost:8765"; Start-Process "http://localhost:8765"
} else { Mal "El lienzo no responde en el puerto 8765 (revisa: docker compose logs lienzo)" }
if (Puerto "127.0.0.1" 3000) { Ok "Grafana en http://localhost:3000" } else { Aviso "Grafana aun no responde en el puerto 3000" }

Paso "FIN"
Info ("Fin: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + ". Registro completo en logs\arranque.log")
