$ErrorActionPreference = 'Continue'
# Control REAL protegido del MCT-09. No arranca el equipo: espera una orden
# confirmada desde el SCADA y solo puede escribir %M30 y %MW100.
$py = 'py'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $dir 'temperatura_control.log'
$env:CONTROL_TEMPERATURA_REAL = '1'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Control temperatura armado (M30/MW100 solamente)" | Out-File -Append -FilePath $log
while ($true) {
  & $py -3 -u "$dir\conector_control_temperatura.py" --plc 192.168.114.10 --broker 127.0.0.1 --puerto 1883 --habilitado-real *>> $log
  "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Conector temperatura detenido; reinicio en 5 s" | Out-File -Append -FilePath $log
  Start-Sleep -Seconds 5
}
