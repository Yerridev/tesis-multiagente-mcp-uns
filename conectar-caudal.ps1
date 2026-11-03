$ErrorActionPreference = 'Stop'
$ip = '192.168.114.70'
$plc = '192.168.114.7'

if (Get-NetIPAddress -IPAddress $ip -ErrorAction SilentlyContinue) {
    Write-Host "La IP $ip ya está configurada en esta PC."
    exit 0
}

if (Test-Connection $ip -Count 1 -Quiet -ErrorAction SilentlyContinue) {
    throw "La IP $ip responde en la red; no se puede asignar a esta PC."
}

New-NetIPAddress -InterfaceAlias 'Ethernet' -IPAddress $ip -PrefixLength 24 -SkipAsSource $false | Out-Null
Write-Host "IP $ip añadida temporalmente. PLC de caudal: $plc."
Write-Host 'El conector de caudal debe usar --source-ip 192.168.114.70 y TSAP 1000.'
