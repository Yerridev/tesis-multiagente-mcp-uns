$dir = $PSScriptRoot
foreach ($n in 'presion_edge','temperatura_edge','caudal_edge','temperatura_control') {
  $s = Join-Path $dir "launch_$n.ps1"
  $corre = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*launch_$n.ps1*" }
  if ($corre) { "ya corria $n" } else {
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$s`"" -WindowStyle Hidden
    "arrancado $n" }
}
