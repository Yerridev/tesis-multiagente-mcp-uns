# Simulador de los 4 modulos del laboratorio (todo en Python)

PLC virtuales con el MISMO mapa de memoria y protocolo que los reales, mas un modelo fisico de cada planta.
Los conectores (edge y control), el SCADA y los agentes MCP funcionan contra ellos solo cambiando la IP a 127.0.0.1.

| Modulo | PLC emulado | Protocolo / puerto | Comando |
|---|---|---|---|
| Temperatura MCT-09 | Twido | Modbus TCP 502 | `python -m simulador.temperatura` |
| Caudal MCC-09 | S7-200 + CP243-1 | S7 (snap7) 102 | `python -m simulador.caudal` |
| Nivel MCN-09 | MicroLogix 1100 | EtherNet/IP-PCCC 44818 | `python -m simulador.nivel` |
| Presion MCP-09 | cFP-2200 (LabVIEW RT) | variables JSON 6341 (*) | `python -m simulador.presion` |

(*) NI-PSP/DataSocket es propietario: el simulador sirve las mismas variables por JSON y los conectores de
presion se ejecutan con el shim `simulador/psp_shim` en PYTHONPATH (falso `win32com`/`pythoncom`), sin tocar su codigo.

Requisitos (ya estan en el .venv del historiador): `python-snap7`, `pycomm3`, `pymodbus`, `paho-mqtt`.

## Opciones comunes
`--acelerar 10` (tiempo 10x)  `--escenario simulador/escenarios/<x>.json`  `--semilla 1`  `--log 10`  `--host 0.0.0.0`

## Conectores contra el simulador (ejecutar desde la raiz del proyecto)
```
python conectores\conector_edge_twido.py   --plc 127.0.0.1 --broker 127.0.0.1
python conectores\conector_edge_s7200.py   --plc 127.0.0.1 --broker 127.0.0.1 --local-tsap 1000 --remote-tsap 1000
python conectores\conector_edge_ml1100.py  --plc 127.0.0.1 --broker 127.0.0.1
set PYTHONPATH=%CD%\simulador\psp_shim
python conectores\conector_edge_cfp2200.py --cfp 127.0.0.1 --broker 127.0.0.1
```
Los conectores de control usan los mismos `--plc` / `--cfp`. No pongas `--source-ip` del caudal con el simulador.

## Escenarios (fallas inyectadas)
`temperatura_*.json`, `caudal_fallas.json`, `nivel_fallas.json`, `presion_fallas.json`: cambios de SP, fallas de
nivel, sensor congelado, fugas/obstruccion, falta de agua y caida del PLC (para probar alarmas y agentes).

## Limites
La logica de escalera/RT es una reconstruccion (respaldos + pruebas del laboratorio) y los parametros fisicos son
estimados: sirve para probar software, no para sintonizar PID del equipo real.
