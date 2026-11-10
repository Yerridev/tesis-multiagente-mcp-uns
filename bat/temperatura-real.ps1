# Revisa y arranca el lector REAL de temperatura (Twido 192.168.114.10, Modbus 502)
$raiz = Split-Path -Parent $PSScriptRoot
$con  = Join-Path $raiz 'conectores'
$log  = Join-Path $con 'temperatura_edge.log'
$ip   = '192.168.114.10'

Write-Host "`n[1/5] Cable de la red del laboratorio (Ethernet)..." -ForegroundColor Cyan
$ad = Get-NetAdapter -Name 'Ethernet' -ErrorAction SilentlyContinue
if ($ad.Status -ne 'Up') { Write-Host "  SIN ENLACE ($($ad.Status)): conecta el cable y corre red-laboratorio.bat" -ForegroundColor Red; return }
$ips = (Get-NetIPAddress -InterfaceAlias 'Ethernet' -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress -join ', '
Write-Host "  OK  IP: $ips"

Write-Host "`n[2/5] Ping al Twido $ip..." -ForegroundColor Cyan
if (Test-Connection $ip -Count 2 -Quiet) { Write-Host '  responde' -ForegroundColor Green } else { Write-Host '  NO responde al ping (revisa que el PLC este encendido y su cable al switch)' -ForegroundColor Red }

Write-Host "`n[3/5] Puerto Modbus 502..." -ForegroundColor Cyan
$tcp = New-Object Net.Sockets.TcpClient
$ok = $tcp.BeginConnect($ip, 502, $null, $null).AsyncWaitHandle.WaitOne(2000) -and $tcp.Connected
$tcp.Close()
if ($ok) { Write-Host '  502 abierto: el PLC acepta conexiones' -ForegroundColor Green }
else { Write-Host '  502 NO responde. Si TwidoSuite esta abierto, CIERRALO (el Twido admite pocas conexiones)' -ForegroundColor Red }
$ts = Get-Process | Where-Object { $_.ProcessName -match 'Twido' }
if ($ts) { Write-Host "  AVISO: TwidoSuite abierto (PID $($ts.Id -join ',')) - cierralo" -ForegroundColor Yellow }

Write-Host "`n[4/5] Lector de temperatura (launch_temperatura_edge.ps1)..." -ForegroundColor Cyan
$corre = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*launch_temperatura_edge.ps1*' }
if ($corre) { Write-Host "  ya estaba corriendo (PID $($corre.ProcessId))" }
else {
  Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$con\launch_temperatura_edge.ps1`"" -WindowStyle Hidden
  Write-Host '  no corria: ARRANCADO (no esta en el arranque automatico de Windows)' -ForegroundColor Green
}

Write-Host "`n[5/5] Ultimas lineas del log (espero 8 s)..." -ForegroundColor Cyan
Start-Sleep -Seconds 8
Get-Content $log -Tail 12 -ErrorAction SilentlyContinue | ForEach-Object { "  $_" }
