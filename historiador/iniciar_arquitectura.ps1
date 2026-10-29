# Arranque de la arquitectura de tesis v2 (solo lectura): PLCs -> conectores -> MQTT/UNS -> TimescaleDB/Grafana -> MCP
# Uso: doble clic en INICIAR_TODO.bat (o: powershell -ExecutionPolicy Bypass -File iniciar_arquitectura.ps1)
#
# Principio: cada equipo es INDEPENDIENTE. Si un PLC esta apagado se informa y el arranque sigue con los demas.
#   - Caudal  (S7-200, 192.168.114.7)      -> conector en esta laptop (ventana propia, se reinicia solo)
#   - Nivel   (MicroLogix, 192.168.114.9)  -> conector en esta laptop (ventana propia, se reinicia solo)
#   - Presion (cFP-2200, 192.168.114.8)    -> conector en la VM Windows 7 (DataSocket); este script enciende la VM
#   - Temperatura (Twido, 192.168.114.10)  -> conector en esta laptop (Modbus TCP 502, ventana propia, se reinicia solo)
# Los conectores reintentan solos: un PLC que se enciende DESPUES se integra sin volver a ejecutar este script.
# Todo queda registrado en historiador\logs\arranque.log (version anterior: respaldo_2026-10-19\iniciar_arquitectura_v1.ps1)
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
function Ping($ip) { try { return [bool](Test-Connection -ComputerName $ip -Count 2 -Quiet -ErrorAction SilentlyContinue) } catch { return $false } }

Info ("Inicio: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "  carpeta: $Raiz")

$Uns = "uss/campus/lab-automatizacion/sl01la07"
$Equipos = @(
    [ordered]@{ id = "caudal-mcc09";  nombre = "Caudal MCC-09 (S7-200)";       ip = "192.168.114.7"; puerto = 102;
                donde = "laptop"; script = "conector_edge_s7200.py";  mods = "snap7, paho.mqtt";   pip = "python-snap7 paho-mqtt";
                mcp = "servidor_mcp.py" },
    [ordered]@{ id = "nivel-mcn09";   nombre = "Nivel MCN-09 (MicroLogix 1100)"; ip = "192.168.114.9"; puerto = 44818;
                donde = "laptop"; script = "conector_edge_ml1100.py"; mods = "pycomm3, paho.mqtt"; pip = "pycomm3 paho-mqtt";
                mcp = "servidor_mcp_nivel.py" },
    [ordered]@{ id = "presion-mcp09"; nombre = "Presion MCP-09 (cFP-2200)";    ip = "192.168.114.8"; puerto = $null;
                donde = "vm";     script = "conector_edge_cfp2200.py"; mods = ""; pip = "";
                mcp = "servidor_mcp_presion.py" },
    [ordered]@{ id = "temperatura-mct09"; nombre = "Temperatura MCT-09 (Twido)"; ip = "192.168.114.10"; puerto = 502;
                donde = "laptop"; script = "conector_edge_twido.py"; mods = "pymodbus, paho.mqtt"; pip = "pymodbus paho-mqtt";
                mcp = "servidor_mcp_temperatura.py" }
)
$Estado = @{}
foreach ($e in $Equipos) { $Estado[$e.id] = [ordered]@{ red = "?"; conector = "?"; datos = "?"; detalle = "" } }

# ---------------------------------------------------------------- 1. .env
Paso "1. Configuracion (.env)"
$Cfg = @{}
if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match "^\s*[A-Z_]+=" } | ForEach-Object { $k, $v = $_ -split "=", 2; $Cfg[$k.Trim()] = $v.Trim() }
    Ok (".env encontrado (" + $Cfg.Count + " claves)")
} else { Mal "No existe .env (copia .env.example a .env y vuelve a ejecutar)"; exit 1 }
$DbUser = $Cfg["DB_USER"]; $DbName = $Cfg["DB_NAME"]; $LectorPwd = $Cfg["MCP_READER_PASSWORD"]
if (-not $Cfg.ContainsKey("LLM_PROVEEDOR")) {
    Add-Content -Encoding UTF8 ".env" "`nLLM_PROVEEDOR=gemini`nGEMINI_MODEL=gemini-3.8-flash"
    $Cfg["LLM_PROVEEDOR"] = "gemini"; Info "Se agrego LLM_PROVEEDOR=gemini al .env"
}
if (-not $Cfg.ContainsKey("GEMINI_API_KEY")) { Add-Content -Encoding UTF8 ".env" "GEMINI_API_KEY="; $Cfg["GEMINI_API_KEY"] = "" }
$Prov = $Cfg["LLM_PROVEEDOR"]
$ClaveLlm = switch ($Prov) {
    "anthropic"  { "ANTHROPIC_API_KEY" }
    "gemini"     { "GEMINI_API_KEY" }
    "openrouter" { "OPENROUTER_API_KEY" }
    default      { "LLM_API_KEY" }
}
if ($Cfg[$ClaveLlm]) { Ok "Agente del lienzo: proveedor $Prov, clave $ClaveLlm configurada" + $(if ($Cfg["OPENROUTER_MODEL"] -and $Prov -eq "openrouter") { " (modelo $($Cfg["OPENROUTER_MODEL"]))" } else { "" }) }
else { Aviso "Agente del lienzo: proveedor $Prov sin clave ($ClaveLlm vacia en el .env); el lienzo funciona sin chat" }

# ---------------------------------------------------------------- 2. Red y equipos
Paso "2. Red del laboratorio y equipos (un equipo apagado NO detiene el arranque)"
$ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty IPAddress)
Info ("IPs de esta laptop: " + ($ips -join ", "))
if ($ips -contains "192.168.114.12") { Ok "La laptop tiene 192.168.114.12 (IP de la laptop de tesis; broker MQTT de la VM de presion)" }
else { Aviso "La laptop NO tiene 192.168.114.12: la VM de presion no encontrara el broker MQTT (CONECTOR_CFP2200.bat usa .12)" }
if ($ips -contains "192.168.114.10") { Ok "La laptop tiene 192.168.114.10 (cliente autorizado del enlace 1 del S7-200)" }
else { Aviso "La laptop NO tiene 192.168.114.10: el conector de caudal no podra leer el S7-200 (el enlace 1 del CP243-1 solo acepta .10, que hoy ocupa el Twido de temperatura; ver red_laboratorio_plc.md)" }
foreach ($e in $Equipos) {
    $vivo = Ping $e.ip
    if ($vivo -and $e.puerto) { $vivo = Puerto $e.ip $e.puerto }
    if ($vivo) { $Estado[$e.id].red = "ENCENDIDO"; Ok "$($e.nombre) responde en $($e.ip)" }
    else { $Estado[$e.id].red = "APAGADO"; Aviso "$($e.nombre) NO responde en $($e.ip): se continua sin el (su conector queda esperando)" }
}

# ---------------------------------------------------------------- 3. Mosquitto
Paso "3. Broker MQTT (Mosquitto)"
if (-not (Puerto "127.0.0.1" 1883)) {
    $svc = Get-Service -Name mosquitto -ErrorAction SilentlyContinue
    if ($svc) { Info "Servicio mosquitto: $($svc.Status). Intentando iniciarlo..."; try { Start-Service mosquitto -ErrorAction Stop } catch { Aviso "No se pudo iniciar el servicio (requiere administrador): $_" }; Start-Sleep 3 }
}
$MqttOk = Puerto "127.0.0.1" 1883
if ($MqttOk) { Ok "Mosquitto escuchando en 1883" } else { Mal "Mosquitto no escucha en 1883. Inicia el servicio 'Mosquitto Broker' como administrador. Los conectores reintentaran solos." }
$conf = "C:\Program Files\mosquitto\mosquitto.conf"
if (Test-Path $conf) {
    $c = Get-Content $conf | Where-Object { $_ -notmatch "^\s*#" -and $_.Trim() -ne "" }
    Info ("mosquitto.conf (lineas activas): " + ($c -join " | "))
    if (-not ($c -match "listener\s+1883\s+0\.0\.0\.0")) { Aviso "mosquitto.conf no tiene 'listener 1883 0.0.0.0': Docker y la VM de presion no podran conectarse" }
}
if (Get-Command Get-NetFirewallRule -ErrorAction SilentlyContinue) {
    if (-not (Get-NetFirewallRule -DisplayName "Mosquitto 1883" -ErrorAction SilentlyContinue)) {
        Aviso "No hay regla de firewall 'Mosquitto 1883': la VM de presion no podra publicar (ver guia: New-NetFirewallRule ... -LocalPort 1883)"
    }
}

# ---------------------------------------------------------------- 4. Docker
Paso "4. Docker: TimescaleDB, ingestores (4), Grafana y lienzo"
$DockerOk = $false
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Aviso "Docker no responde. Abriendo Docker Desktop y esperando hasta 2 min..."
    $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dd) { Start-Process $dd }
    for ($i = 0; $i -lt 24; $i++) { Start-Sleep 5; docker info *> $null; if ($LASTEXITCODE -eq 0) { break } }
}
docker info *> $null
if ($LASTEXITCODE -eq 0) {
    Ok "Docker responde"
    docker compose up -d --build 2>&1 | ForEach-Object { Info "  $_" }
    Info "Esperando a TimescaleDB..."
    for ($i = 0; $i -lt 30; $i++) { docker exec uns-timescaledb pg_isready -U $DbUser -d $DbName *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 2 }
    if ($LASTEXITCODE -eq 0) { $DockerOk = $true; Ok "TimescaleDB lista" } else { Mal "TimescaleDB no responde: se omiten los pasos de base de datos" }
    docker compose ps 2>&1 | ForEach-Object { Info "  $_" }
} else { Mal "Docker no responde: los conectores igual se lanzan (publican en MQTT), pero no habra historiador, Grafana ni lienzo" }

function Sql($q) {
    if (-not $DockerOk) { return $null }
    $r = docker exec uns-timescaledb psql -U $DbUser -d $DbName -t -A -c $q 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($r | Select-Object -First 1)
}

# ---------------------------------------------------------------- 5. Migraciones (una sola vez cada una)
Paso "5. Migraciones de la base"
if ($DockerOk) {
    $marca = Join-Path $Raiz "db\.migracion_v32_aplicada"
    if (Test-Path $marca) { Ok "Caudal v3.2: ya aplicada" }
    else {
        Get-Content -Raw "db\04_migracion_v32.sql" | docker exec -i uns-timescaledb psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1 2>&1 | ForEach-Object { Info "  $_" }
        if ($LASTEXITCODE -eq 0) { Get-Date | Set-Content $marca; Ok "Caudal v3.2 aplicada" } else { Aviso "La migracion de caudal v3.2 fallo (ver lineas anteriores); se continua" }
    }
    $hayPresion = Sql "SELECT count(*) FROM rangos_validados WHERE variable = 'presion-mcp09/presion/psi'"
    if ($hayPresion -and [int]$hayPresion -gt 0) { Ok "Presion v0.1: ya aplicada" }
    else {
        Get-Content -Raw "db\06_presion_v01.sql" | docker exec -i uns-timescaledb psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1 2>&1 | ForEach-Object { Info "  $_" }
        if ($LASTEXITCODE -eq 0) { Ok "Presion v0.1 aplicada" } else { Aviso "La migracion de presion fallo (ver lineas anteriores); se continua" }
    }
    $hayTemp = Sql "SELECT count(*) FROM rangos_validados WHERE variable = 'temperatura-mct09/temperatura/principal_c'"
    if ($hayTemp -and [int]$hayTemp -gt 0) { Ok "Temperatura v0.1: ya aplicada" }
    else {
        Get-Content -Raw "db\07_temperatura_v01.sql" | docker exec -i uns-timescaledb psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1 2>&1 | ForEach-Object { Info "  $_" }
        if ($LASTEXITCODE -eq 0) { Ok "Temperatura v0.1 aplicada" } else { Aviso "La migracion de temperatura fallo (ver lineas anteriores); se continua" }
    }
} else { Aviso "Sin base de datos: se omiten las migraciones" }

# ---------------------------------------------------------------- 6. Python
Paso "6. Entornos de Python"
$Venv = Join-Path $Raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $Venv)) { Info "Creando .venv..."; python -m venv .venv }
if (Test-Path $Venv) {
    & $Venv -m pip install -q --disable-pip-version-check -r mcp_servidor\requirements.txt 2>&1 | ForEach-Object { Info "  $_" }
} else { Mal "No se pudo crear .venv (Python no esta instalado o no esta en el PATH)" }

function PythonPara($mods, $pip) {
    # Prefiere el Python que ya tiene las librerias del conector (probado con el PLC); si no, las instala en el .venv.
    foreach ($cand in @("python", "py")) {
        $exe = (Get-Command $cand -ErrorAction SilentlyContinue).Source
        if ($exe) { & $exe -c "import $mods" *> $null; if ($LASTEXITCODE -eq 0) { return $exe } }
    }
    if (Test-Path $Venv) {
        Info "Instalando $pip en el .venv..."
        & $Venv -m pip install -q --disable-pip-version-check $pip.Split(" ") 2>&1 | ForEach-Object { Info "  $_" }
        & $Venv -c "import $mods" *> $null
        if ($LASTEXITCODE -eq 0) { return $Venv }
    }
    return $null
}

# ---------------------------------------------------------------- 7. Conectores en esta laptop (caudal, nivel y temperatura)
Paso "7. Conectores edge en esta laptop (se lanzan aunque el PLC este apagado: esperan y reintentan solos)"
foreach ($e in ($Equipos | Where-Object { $_.donde -eq "laptop" })) {
    $script = $e.script
    # Detener instancias anteriores (primero la ventana que las reinicia, luego Python)
    Get-CimInstance Win32_Process -Filter "Name like 'powershell%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$script*" -and $_.ProcessId -ne $PID } |
        ForEach-Object { Info "Cerrando ventana anterior de $script (PID $($_.ProcessId))"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$script*" } |
        ForEach-Object { Info "Deteniendo conector anterior $script (PID $($_.ProcessId))"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    try {
        $py = PythonPara $e.mods $e.pip
        if (-not $py) { Mal "$($e.nombre): no hay Python con $($e.mods); conector NO lanzado"; $Estado[$e.id].conector = "SIN PYTHON"; continue }
        $logCon = Join-Path $Logs ("conector_" + $e.id + ".log")
        $titulo = "CONECTOR " + $e.nombre
        $cmd = "`$host.UI.RawUI.WindowTitle='$titulo'; Set-Location '$Raiz'; `$env:PYTHONUNBUFFERED='1'; " +
               "while (`$true) { & '$py' $script 2>&1 | Tee-Object -FilePath '$logCon' -Append; " +
               "Write-Host 'El conector se detuvo. Reinicio en 10 s (cierra esta ventana para detenerlo)...' -ForegroundColor Yellow; Start-Sleep 10 }"
        Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $cmd
        $Estado[$e.id].conector = "LANZADO"
        Ok "$($e.nombre): conector lanzado en su ventana (log: logs\conector_$($e.id).log)"
    } catch { Mal "$($e.nombre): no se pudo lanzar el conector: $_"; $Estado[$e.id].conector = "ERROR" }
}

# ---------------------------------------------------------------- 8. Presion: VM Windows 7 con DataSocket
Paso "8. Conector de presion (VM Windows 7)"
$pres = $Equipos | Where-Object { $_.id -eq "presion-mcp09" }
$VBox = Join-Path $env:ProgramFiles "Oracle\VirtualBox\VBoxManage.exe"
try {
    if (-not (Test-Path $VBox)) { Aviso "VirtualBox no encontrado: enciende la VM de presion a mano"; $Estado[$pres.id].conector = "VM MANUAL" }
    else {
        $vmNombre = $Cfg["VM_PRESION"]
        if (-not $vmNombre) {
            $vm = & $VBox list vms 2>$null | Where-Object { $_ -match 'LAB-AUTOMATIZACION' } | Select-Object -First 1
            if ($vm -match '^"(.+)"') { $vmNombre = $Matches[1] }
        }
        if (-not $vmNombre) { Aviso "No se encontro la VM (agrega VM_PRESION=<nombre exacto> al .env)"; $Estado[$pres.id].conector = "VM NO ENCONTRADA" }
        else {
            $corriendo = & $VBox list runningvms 2>$null | Where-Object { $_ -like "*`"$vmNombre`"*" }
            if ($corriendo) { Ok "VM '$vmNombre' ya esta encendida" }
            else {
                Info "Encendiendo la VM '$vmNombre'..."
                & $VBox startvm "$vmNombre" --type gui 2>&1 | ForEach-Object { Info "  $_" }
            }
            $Estado[$pres.id].conector = "EN LA VM"
        }
    }
} catch { Aviso "No se pudo manejar la VM: $_"; $Estado[$pres.id].conector = "VM ERROR" }
if ($DockerOk) {
    Info "Esperando el latido del conector de presion (hasta 2 min; arranca solo con Windows en la VM)..."
    $topic = "$Uns/presion-mcp09/funcional/edge/heartbeat"
    for ($i = 0; $i -lt 24; $i++) {
        $edad = Sql "SELECT coalesce(extract(epoch FROM now() - max(time))::int, 99999) FROM eventos WHERE topic = '$topic'"
        if ($edad -and [int]$edad -lt 30) { break }
        Start-Sleep 5
    }
    if ($edad -and [int]$edad -lt 30) { Ok "Conector de presion publicando (latido hace $edad s)" }
    else { Aviso "Sin latido del conector de presion. En la VM ejecuta CONECTOR_CFP2200.bat (o ponlo en shell:startup para que arranque solo)" }
}

# ---------------------------------------------------------------- 9. Datos en vivo por equipo
Paso "9. Datos en vivo por equipo"
Info "Esperando 20 s a que los conectores publiquen..."
Start-Sleep 20
foreach ($e in $Equipos) {
    $base = "$Uns/$($e.id)/funcional"
    $edad = Sql "SELECT coalesce(extract(epoch FROM now() - max(time))::int, 99999) FROM eventos WHERE topic = '$base/edge/heartbeat'"
    $plc  = Sql "SELECT texto FROM eventos WHERE topic = '$base/plc/conexion' ORDER BY time DESC LIMIT 1"
    if ($null -eq $edad) { $Estado[$e.id].datos = "SIN BASE" }
    elseif ([int]$edad -lt 30 -and $plc -eq "CONECTADO") { $Estado[$e.id].datos = "EN VIVO"; Ok "$($e.nombre): datos en vivo (latido hace $edad s)" }
    elseif ([int]$edad -lt 30) { $Estado[$e.id].datos = "CONECTOR SIN PLC"; Aviso "$($e.nombre): el conector corre pero el PLC no responde ($plc)" }
    else { $Estado[$e.id].datos = "SIN DATOS"; Aviso "$($e.nombre): sin datos en vivo" }
}
foreach ($c in @("uns-ingestor", "uns-ingestor-nivel", "uns-ingestor-presion", "uns-ingestor-temperatura")) {
    if ($DockerOk) { docker logs --tail 3 $c 2>&1 | ForEach-Object { Info "  $c> $_" } }
}

# ---------------------------------------------------------------- 10. Servidores MCP
Paso "10. Servidores MCP (prueba rapida de cada uno)"
$env:MCP_DSN = "postgresql://mcp_lector:$LectorPwd@localhost:5432/$DbName"
if ($DockerOk -and (Test-Path $Venv)) {
    foreach ($e in $Equipos) {
        $LogMcp = Join-Path $Logs ("mcp_probar_" + $e.id + ".log")
        try {
            & $Venv (Join-Path "mcp_servidor" $e.mcp) --probar 2>&1 | ForEach-Object { "$_" } | Out-File -Encoding utf8 $LogMcp
            $errs = @(Select-String -Path $LogMcp -Pattern "^ERROR").Count
            $diag = Select-String -Path $LogMcp -Pattern '"diagnostico":' | Select-Object -First 1
            if ($errs -eq 0) { Ok "$($e.mcp): sin errores $(if ($diag) { '- ' + $diag.Line.Trim() })" }
            else { Aviso "$($e.mcp): $errs herramienta(s) con error (ver logs\mcp_probar_$($e.id).log)" }
        } catch { Aviso "$($e.mcp): no se pudo probar: $_" }
    }
} else { Aviso "Sin base de datos o sin .venv: se omite la prueba de los servidores MCP" }

# ---------------------------------------------------------------- 11. Claude Desktop
Paso "11. Configuracion de Claude Desktop (4 servidores MCP)"
$cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
try {
    if (Test-Path $cfgPath) { $cfg = Get-Content -Raw $cfgPath | ConvertFrom-Json }
    else { New-Item -ItemType Directory -Force -Path (Split-Path $cfgPath) | Out-Null; $cfg = New-Object PSObject }
    if (-not $cfg.PSObject.Properties["mcpServers"]) { $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue (New-Object PSObject) }
    $cambios = 0
    foreach ($e in $Equipos) {
        $ruta = Join-Path $Raiz ("mcp_servidor\" + $e.mcp)
        $act = $cfg.mcpServers.PSObject.Properties[$e.id]
        if ($act -and $act.Value.command -eq $Venv -and @($act.Value.args)[0] -eq $ruta) { continue }
        $srv = [PSCustomObject]@{ command = $Venv; args = @($ruta); env = [PSCustomObject]@{ MCP_DSN = $env:MCP_DSN } }
        if ($act) { $cfg.mcpServers.($e.id) = $srv } else { $cfg.mcpServers | Add-Member -NotePropertyName $e.id -NotePropertyValue $srv }
        $cambios++
    }
    if ($cambios -gt 0) {
        if (Test-Path $cfgPath) { Copy-Item $cfgPath "$cfgPath.respaldo_$(Get-Date -Format yyyyMMdd_HHmmss)" }
        [IO.File]::WriteAllText($cfgPath, ($cfg | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
        Ok "$cambios servidor(es) MCP registrados en Claude Desktop (reinicia Claude Desktop para activarlos)"
    } else { Ok "Claude Desktop ya tiene los 4 servidores MCP (caudal, nivel, presion, temperatura)" }
} catch { Aviso "No se pudo revisar la configuracion de Claude Desktop: $_" }

# ---------------------------------------------------------------- 12. Lienzo vivo y Grafana
Paso "12. Lienzo vivo y Grafana"
if ($DockerOk) {
    for ($i = 0; $i -lt 20; $i++) { if (Puerto "127.0.0.1" 8765) { break }; Start-Sleep 2 }
    if (Puerto "127.0.0.1" 8765) {
        try { $s = Invoke-RestMethod "http://127.0.0.1:8765/api/salud" -TimeoutSec 5; Info ("  salud del lienzo: db=" + $s.db + " mqtt=" + $s.mqtt + " agente=" + $s.agente + " equipos=" + ($s.equipos_cargados -join ",")) } catch { Aviso "El lienzo responde pero /api/salud fallo: $_" }
        Ok "Lienzo vivo en http://localhost:8765"; Start-Process "http://localhost:8765"
    } else { Aviso "El lienzo no responde en el puerto 8765 (revisa: docker compose logs lienzo)" }
    if (Puerto "127.0.0.1" 3000) { Ok "Grafana en http://localhost:3000" } else { Aviso "Grafana aun no responde en el puerto 3000" }
}

# ---------------------------------------------------------------- RESUMEN
Paso "RESUMEN"
$fila = "{0,-34} {1,-11} {2,-18} {3}"
Info ($fila -f "Equipo", "Red", "Conector", "Datos")
Info ($fila -f "------", "---", "--------", "-----")
foreach ($e in $Equipos) { $s = $Estado[$e.id]; Info ($fila -f $e.nombre, $s.red, $s.conector, $s.datos) }
$vivos = @($Equipos | Where-Object { $Estado[$_.id].datos -eq "EN VIVO" }).Count
Info ""
Info "$vivos de $($Equipos.Count) equipos con datos en vivo. Los apagados se integran solos cuando se enciendan (no hace falta repetir este arranque)."
Info ("Fin: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + ". Registro completo en logs\arranque.log")
