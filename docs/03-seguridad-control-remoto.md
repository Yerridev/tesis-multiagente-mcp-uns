# 03 · Seguridad del control remoto — nivel-mcn09

*Postura de seguridad del prototipo de integración MCP (MCP-INDUSTRIAL-NET), 29-oct-2026.*

## 1. Principios vigentes

1. **El backend nunca escribe al PLC.** Solo valida, audita y publica la orden en MQTT.
2. **Doble gate de escritura**: backend (triple gate REAL) + conector (allowlist VERIFICADA
   + `CONTROL_REAL=1` + `--habilitado-real` + selector REMOTO con lectura fresca `I:0/0`).
3. **Comandos semánticos solamente**: el navegador envía `{tipo, valor, unidad}`, jamás una
   dirección del PLC. La dirección la resuelve el conector contra su allowlist.
4. **Salidas prohibidas por código**: `O:0/*`, `O:1/*`, `I:*`, `S:*` → `DIRECCION_PROHIBIDA`
   (guard en backend y conector; no depende de que la allowlist cambie).
5. **Trazabilidad total**: cada orden lleva id, usuario, rol, correlación, comentario, origen,
   fechas de creación/expiración y queda en auditoría JSONL append-only.
6. **Confirmación real**: `CONFIRMADO` exige una lectura posterior coincidente; la entrega
   MQTT nunca cierra una orden.

## 2. Papel del agente de IA (limitado por diseño)

| Puede | No puede |
|---|---|
| Consultar estado de equipos/órdenes | Iniciar o detener la bomba |
| Explicar alarmas y diagnósticos | Cambiar setpoint o parámetros PID |
| Recomendar una revisión / procedimiento | Abrir o cerrar válvulas |
| Mostrar el checklist de laboratorio | Activar el modo REAL (`CONTROL_REAL`) |
| Generar reportes de auditoría | Modificar la allowlist o los roles |

El agente del prototipo (`OpenRouterAgent`/`AgentService`) solo tiene herramientas de
lectura (`estado_planta`, `leer_equipo`, `verificar_alarma`, `resumen_historico`,
`estado_plc`); no existe ninguna herramienta de control.

## 3. Arquitectura de red (recomendada antes de cualquier REAL)

- **El PLC MicroLogix 1100 NUNCA se conecta a Internet.** Solo al segmento OT
  `192.168.114.0/24`, aislado.
- **Segmentación OT/IT**: firewall entre la red administrativa (donde vive la laptop
  `.90` con la API) y el laboratorio. Reglas mínimas: solo TCP 44818 (EtherNet/IP) desde
  la laptop hacia `.9`; MQTT solo en loopback/lan interna; nada de puerta a puerta.
- **HTTPS** en la API .NET en cualquier exposición fuera de localhost (hoy `http://localhost:5294`).
- **Sustitución de credenciales dev**: las claves `dev-*` (`Control:Usuarios`) son de
  desarrollo. Reemplazar por **OIDC/JWT** (p. ej. Entra ID/Auth0) conservando la matriz
  viewer < operador < supervisor < admin.
- **Secretos en variables de entorno**: OpenRouter (`appsettings.json` hoy contiene una
  clave expuesta — ver §4), credenciales de DB y Grafana.
- **Auditoría persistente**: JSONL diario (`auditoria/control-YYYYMMDD.jsonl`) + copia a
  almacenamiento inmutable; el endpoint `/api/control/auditoria` exige supervisor.
- **Copia de seguridad del programa RSS**: versionar `upload final.RSS` + los backups
  `BAK10x` en repositorio privado con checksums; cualquier campaña de laboratorio empieza
  por verificar que el backup coincide con lo cargado en el PLC.
- **Desactivar servidores web heredados**: el SCADA LabVIEW de nivel trae
  `niwebserver.conf` con `Listen 80` y `NIVEL.html` con ActiveX/FTP (`ftp://ftp.ni.com`).
  No usar esas páginas; mantener `WebServer.Enabled=False` (estado actual de `NIVEL.ini`).

## 4. Hallazgos de seguridad (registros)

| # | Hallazgo | Acción |
|---|---|---|
| S1 | Clave de OpenRouter visible en `backend/appsettings.json` (y copias) | **Rotar la clave en el panel de OpenRouter** de inmediato; pasarla a variable de entorno `OPENROUTER__ApiKey` o user-secrets; borrarla del historial git |
| S2 | Servidor web LabVIEW heredado (FTP/ActiveX, puerto 80) | Mantener deshabilitado; no publicar `NIVEL.html` |
| S3 | Bearer de desarrollo en el frontend (`dev-supervisor` por defecto) | Aceptable solo en lab; bloquear con feature-flag para cualquier exposición |
| S4 | API sin HTTPS/TLS | Añadir certificado antes de salir de localhost |
| S5 | Sin firewall documentado entre OT e IT | Implementar antes del modo REAL |

## 5. Procedimiento de retorno a modo LOCAL (pánico)

1. Selector físico a **LOCAL** (el PLC ignora cualquier orden remota).
2. Backend: `Control:HabilitadoEscritura=false` y eliminar la variable `CONTROL_REAL`.
3. Detener `conector_control_nivel.py`.
4. Verificar en el panel físico que bomba/válvula responden solo al mando local.
5. Registrar el evento en la auditoría (quién, cuándo, por qué).

## 6. Última línea de defensa

Incluso con todo mal configurado, el conector rechaza toda escritura mientras exista
**una sola** condición sin cumplir: 0/13 direcciones verificadas ⇒ el modo real es
imposible hasta que personas presentes en el laboratorio verifiquen dirección por
dirección (ver `04-checklist-validacion-presencial.md`).
