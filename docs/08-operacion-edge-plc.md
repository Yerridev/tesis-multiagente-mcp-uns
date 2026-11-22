# 08 · Operación edge y acceso al PLC — MCP-INDUSTRIAL-NET

## 1. Compatibilidad Docker ↔ PLC (medido, no supuesto)

Prueba realizada el 29-oct-2026 desde un contenedor `python:3.12-slim`:

```
PLC 192.168.114.9:44818 -> OK accesible desde contenedor
```

**Conclusión:** Docker Desktop (NAT) **sí** alcanza la red OT `192.168.114.0/24` desde
los contenedores. El conector puede correr contenerizado para lectura/dry-run/simulación.

Reservas que justifican mantener el perfil `edge`:
1. Estabilidad del enlace EtherNet/IP (pycomm3 con tiempos reales) bajo carga del VM
   de Docker.
2. En modo **real** el conector hace pulso + relectura con latencia controlada; en
   Windows host la ruta es más corta y auditable.
3. Fallos de red del host/VM no deben mezclarse con fallos del stack de datos.

## 2. Perfil `edge` (contenedor) vs modo edge-host (recomendado para real)

**Perfil `edge` (contenedor):**
```powershell
$env:CONECTOR_MODO="dry-run"
docker compose --profile edge up -d connector-nivel
```
- corre con las mismas protecciones; NUNCA con `CONTROL_REAL` ni `--habilitado-real`.

**Edge-host (recomendado al acercarse a la campaña de laboratorio):**
```powershell
# en la PC industrial, con el venv de la tesis:
..\04_SISTEMAS-MCP\tesis-multiagente-mcp-uns\historiador\.venv\Scripts\python.exe `
  conectores/conector_control_nivel.py --modo dry-run --broker 127.0.0.1
```
- Usa el Mosquitto local (Windows) y de allí el `mirror-tesis` lo lleva al stack.
- Ventajas: sin red extra de Docker en el camino, logs en consola del operador,
  arranque como tarea programada/servicio Windows.
- La separación **lógica se conserva**: mismo código, mismo contrato, mismos tópicos;
  solo cambia el proceso que lo ejecuta.

## 3. Topología de datos edge (estado actual)

```
PLC 192.168.114.9 ──EtherNet/IP──► conector edge (host, tesis) ──► broker Windows :1883
                                                                    │ (mirror-tesis)
                                                                    ▼
                                                          broker del stack (contenedor)
                                                          ├── backend / agents
                                                          ├── ingestor-nivel → TimescaleDB
                                                          └── connector-nivel (control, DRY-RUN/SIMULADOR)
```

## 4. Reglas al operar cerca del PLC

1. El conector **nunca** se ejecuta con `--modo real` sin el checklist
   (`04-checklist-validacion-presencial.md`) aprobado.
2. Selector físico en LOCAL mientras se pruebe cualquier orden remota.
3. Si Docker reinicia: verificar con `/health/ready` (el PLC aparece como
   `DEGRADADA`, no bloquea el arranque) y con el state del conector
   (`edge.plc` = CONECTADO).
4. Los healthchecks jamás tocan `192.168.114.9`.
5. No exponer Mosquitto/Postgres a la LAN del laboratorio ni del WiFi del portátil.
