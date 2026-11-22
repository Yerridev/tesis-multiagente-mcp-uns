-- Usuarios de aplicación (contraseñas por variable de entorno en el primer arranque
-- se gestionan con ALTER ... PASSWORD en 04_passwords.sql usando variables del compose).
-- ingestor : escritura SOLO en tablas de telemetría (senales/mediciones/equipos).
-- backend_ro / mcp_reader : SOLO lectura.
-- La administración usa el superusuario POSTGRES_USER solo para mantenimiento.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ingestor') THEN
    CREATE ROLE ingestor LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backend_ro') THEN
    CREATE ROLE backend_ro LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcp_reader') THEN
    CREATE ROLE mcp_reader LOGIN;
  END IF;
END
$$;
