-- Esquema del historiador (PostgreSQL estandar). La parte de TimescaleDB va en 02_timescale.sql.

-- Una fila por medicion. "variable" = ruta funcional del UNS (p. ej. 'caudal/pv_pid').
CREATE TABLE IF NOT EXISTS mediciones (
    time       TIMESTAMPTZ      NOT NULL,
    variable   TEXT             NOT NULL,
    valor      DOUBLE PRECISION,
    unidad     TEXT,
    fuente     TEXT             NOT NULL DEFAULT 'uns',   -- 'uns' (en vivo) | 'lvm' (historico LabVIEW)
    direccion  TEXT,                                      -- direccion en el PLC (VD159, Q0.2...) o archivo de origen
    CONSTRAINT mediciones_unica UNIQUE (variable, fuente, time)
);
CREATE INDEX IF NOT EXISTS idx_mediciones_variable_time ON mediciones (variable, time DESC);

-- Mensajes de texto del UNS (ONLINE/OFFLINE, CONECTADO/SIN_CONEXION, heartbeat).
CREATE TABLE IF NOT EXISTS eventos (
    time   TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic  TEXT        NOT NULL,
    texto  TEXT
);
CREATE INDEX IF NOT EXISTS idx_eventos_time ON eventos (time DESC);

-- Catalogo de variables (lo llena el ingestor desde descriptivo/variables del UNS).
CREATE TABLE IF NOT EXISTS variables (
    variable     TEXT PRIMARY KEY,
    tag_plc      TEXT,
    direccion    TEXT,
    unidad       TEXT,
    descripcion  TEXT,
    actualizado  TIMESTAMPTZ DEFAULT now()
);

-- Rango validado por el responsable del laboratorio (lo usa la herramienta MCP comparar_con_rango).
CREATE TABLE IF NOT EXISTS rangos_validados (
    variable   TEXT PRIMARY KEY,
    minimo     DOUBLE PRECISION,
    maximo     DOUBLE PRECISION,
    unidad     TEXT,
    validado_por TEXT,
    nota       TEXT,
    actualizado TIMESTAMPTZ DEFAULT now()
);

-- Rango provisional: el caudalimetro esta calibrado para 0-141 L/min (calibracion_caudalimetro.xls).
-- Reemplazar con el rango operativo que confirme el responsable del laboratorio.
INSERT INTO rangos_validados (variable, minimo, maximo, unidad, validado_por, nota)
VALUES ('caudal/pv_pid', 0, 140, 'L/min', 'PENDIENTE', 'Fondo de escala del programa; falta rango operativo validado'),
       ('caudal/caudalimetro', 0, 141, 'L/min', 'PENDIENTE', 'Rango de calibracion del Kobold DRG; falta rango operativo validado')
ON CONFLICT (variable) DO NOTHING;
