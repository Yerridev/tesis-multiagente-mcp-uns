"== IPs de esta PC"; Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' } | ForEach-Object { "$($_.InterfaceAlias): $($_.IPAddress)" }
"== PLCs"
foreach ($p in @(@('caudal S7-200','192.168.114.7',102), @('presion cFP','192.168.114.8',80), @('nivel ML1100','192.168.114.9',44818), @('temperatura Twido','192.168.114.10',502))) {
  $ping = Test-Connection -ComputerName $p[1] -Count 1 -Quiet -ErrorAction SilentlyContinue
  $tcp = Test-NetConnection -ComputerName $p[1] -Port $p[2] -InformationLevel Quiet -WarningAction SilentlyContinue
  "$($p[0]) $($p[1]): ping=$ping tcp$($p[2])=$tcp"
}
"== procesos de lectores"
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'conector_edge|launch_' } | ForEach-Object { "$($_.ProcessId) $($_.Name) $($_.CreationDate) :: $($_.CommandLine.Substring(0,[Math]::Min(140,$_.CommandLine.Length)))" }
