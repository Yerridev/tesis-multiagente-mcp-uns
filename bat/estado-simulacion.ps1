# Revisa que esta vivo de la PLANTA SIMULADA (solo lee, no cambia nada)
$ok = 0; $mal = 0
function Linea($bien, $texto) {
  if ($bien) { Write-Host "  [OK]    $texto" -ForegroundColor Green; $script:ok++ }
  else       { Write-Host "  [FALTA] $texto" -ForegroundColor Red;   $script:mal++ }
}
$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' }
function Corre($patron) { [bool]($procs | Where-Object { $_.CommandLine -match $patron }) }

Write-Host "`n=== 1. Simuladores (PLC virtuales) ===" -ForegroundColor Cyan
foreach ($m in 'nivel','caudal','presion','temperatura') { Linea (Corre "simulador\.$m") "simulador $m" }

Write-Host "`n=== 2. Conectores hacia los simuladores ===" -ForegroundColor Cyan
Linea (Corre 'conector_edge_cfp2200.*127\.0\.0\.1')      'EDGE presion  (lectura)'
Linea (Corre 'conector_control_presion.*127\.0\.0\.1')   'CONTROL presion (ordenes)'
Linea (Corre 'conector_edge_twido.*127\.0\.0\.1')        'EDGE temperatura (lectura)'
Linea (Corre 'conector_control_temperatura.*127\.0\.0\.1') 'CONTROL temperatura (ordenes)'
Linea (Corre 'conector_edge_s7200.*127\.0\.0\.1')        'EDGE y CONTROL caudal'
Linea (Corre 'conector_edge_ml1100.*127\.0\.0\.1')       'EDGE nivel'
$reales = $procs | Where-Object { $_.CommandLine -match 'conector_\w+\.py' -and $_.CommandLine -notmatch '127\.0\.0\.1' }
foreach ($r in $reales) { Write-Host "  [AVISO] conector apuntando a la planta REAL: $(([regex]::Match($r.CommandLine,'conector_\w+\.py')).Value) PID $($r.ProcessId)" -ForegroundColor Yellow }

Write-Host "`n=== 3. Puertos de los PLC virtuales ===" -ForegroundColor Cyan
foreach ($p in 44818,1102,6341,502) { Linea ([bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) "puerto $p escuchando" }
Linea ([bool](Get-NetTCPConnection -LocalPort 1883 -State Listen -ErrorAction SilentlyContinue)) 'broker Windows 1883'

Write-Host "`n=== 4. Docker ===" -ForegroundColor Cyan
$envs = docker inspect mcp-backend --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
Linea ($envs -match 'MODO_PLANTA=simulado') 'backend en MODO_PLANTA=simulado'
Linea ($envs -match 'PresionControlHost=host.docker.internal') 'backend manda ordenes al broker Windows'
$mir = docker inspect mcp-mirror-tesis --format '{{.State.Running}}' 2>$null
Linea ($mir -eq 'true') 'mirror-tesis corriendo (devuelve los ACK)'

Write-Host ""
if ($mal -eq 0) { Write-Host "TODO OK. Si aun da Timeout corre 07.0_DiagnosticoOrdenes.bat y manda una orden." -ForegroundColor Green }
else { Write-Host "Hay $mal cosa(s) caida(s). Solucion: 04.1_DetenerSimulacion.bat y luego 04.0_SimularPlanta.bat" -ForegroundColor Yellow }
