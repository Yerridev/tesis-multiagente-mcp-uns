-- Seed: equipos del laboratorio (solo metadatos; la telemetría llega por MQTT).
INSERT INTO equipos (equipo, nombre, plc_ip) VALUES
  ('nivel-mcn09',   'Control de nivel MCN-09/001',     '192.168.114.9'),
  ('caudal-mcc09',  'Control de caudal MCC-09/002',    '192.168.114.7'),
  ('presion-mcp09', 'Control de presión MCP-09/001',   '192.168.114.8'),
  ('temperatura-mct09', 'Control de temperatura MCT-09/001', '192.168.114.10')
ON CONFLICT (equipo) DO NOTHING;
