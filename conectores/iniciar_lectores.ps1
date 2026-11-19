# Arranca los lectores REALES que no esten corriendo y muestra si escriben en logs\
$dir  = $PSScriptRoot
$raiz = Split-Path -Parent $dir
Write-Host "`n[1/2] Lanzadores (los mismos del arranque automatico)..." -ForegroundColor Cyan
foreach ($n in 'caudal_edge','nivel_edge','presion_edge','presion_control','temperatura_edge') {
  $s = Join-Path $dir "launch_$n.ps1"
  $corre = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*launch_$n.ps1*" }
  if ($corre) { "  ya corria  $n (PID $($corre.ProcessId -join ','))" }
  else { Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$s`"" -WindowStyle Hidden; "  ARRANCADO  $n" }
}
Write-Host "`n[2/2] Esperando 12 s y revisando logs\ ..." -ForegroundColor Cyan
Start-Sleep -Seconds 12
foreach ($n in 'caudal_edge','nivel_edge','presion_edge','presion_control','temperatura_edge') {
  $log = Join-Path $raiz "logs\$n.log"
  if (-not (Test-Path $log)) { Write-Host "  [SIN LOG] $n  (el lanzador no arranco)" -ForegroundColor Red; continue }
  $ult = Get-Content $log -Tail 2 -ErrorAction SilentlyContinue
  $edad = [int]((Get-Date) - (Get-Item $log).LastWriteTime).TotalSeconds
  $color = if ($edad -le 15) { 'Green' } else { 'Yellow' }
  Write-Host ("  [{0,-4}s] {1}" -f $edad, $n) -ForegroundColor $color
  $ult | ForEach-Object { "         $_" }
}
