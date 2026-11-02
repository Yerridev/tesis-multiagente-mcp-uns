-- Esquema mínimo del prototipo (v1). NO se migra el histórico .lvm automáticamente:
-- eso requiere prueba + respaldo (ver docs/06-despliegue-docker.md).

CREATE TABLE IF NOT EXISTS equipos (
    id          SERIAL PRIMARY KEY,
    equipo      TEXT NOT NULL UNIQUE,
    nombre      TEXT,
    plc_ip      TEXT,
    activo      BOOLEAN NOT NULL DEFAULT TRUE,
    creado      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS senales (
    id          SERIAL PRIMARY KEY,
    equipo_id   INTEGER NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    nombre      TEXT NOT NULL,
    unidad      TEXT,
    source      TEXT,
    UNIQUE (equipo_id, nombre)
);

-- Hipertabla de mediciones: idempotente por (senal_id, ts).
CREATE TABLE IF NOT EXISTS mediciones (
    senal_id    INTEGER NOT NULL REFERENCES senales(id) ON DELETE CASCADE,
    ts          TIMESTAMPTZ NOT NULL,
    valor       DOUBLE PRECISION NOT NULL,
    calidad     TEXT NOT NULL DEFAULT 'ok',
    source      TEXT,
    PRIMARY KEY (senal_id, ts)
);
SELECT create_hypertable('mediciones', 'ts', if_not_exists => TRUE);
SELECT add_retention_policy('mediciones', INTERVAL '365 days', if_not_exists => TRUE);

-- Órdenes de control (espejo del backend para trazabilidad/reportes).
CREATE TABLE IF NOT EXISTS ordenes_control (
    id          TEXT PRIMARY KEY,
    equipo      TEXT NOT NULL,
    tipo        TEXT NOT NULL,
    valor       DOUBLE PRECISION,
    unidad      TEXT,
    estado      TEXT NOT NULL,
    motivo      TEXT,
    usuario     TEXT,
    rol         TEXT,
    modo        TEXT,
    correlacion TEXT,
    expedida    TIMESTAMPTZ,
    actualizada TIMESTAMPTZ,
    raw         JSONB
);

-- Eventos de auditoría (espejo del JSONL del backend).
CREATE TABLE IF NOT EXISTS eventos_auditoria (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    accion      TEXT,
    orden_id    TEXT,
    usuario     TEXT,
    rol         TEXT,
    resultado   TEXT,
    detalle     TEXT
);

-- Índices de frescura/reportes
CREATE INDEX IF NOT EXISTS idx_mediciones_ts ON mediciones (ts DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_orden ON eventos_auditoria (orden_id);

-- Grants: ingestor escribe telemetría; lectores solo leen.
GRANT USAGE ON SCHEMA public TO ingestor, backend_ro, mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backend_ro, mcp_reader;
GRANT SELECT, INSERT, UPDATE ON equipos, senales, mediciones TO ingestor;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ingestor;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO backend_ro, mcp_reader;
