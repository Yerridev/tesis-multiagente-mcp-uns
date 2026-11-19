-- Funciones de TimescaleDB: hypertable, compresion y agregado continuo por minuto.
CREATE EXTENSION IF NOT EXISTS timescaledb;

SELECT create_hypertable('mediciones', by_range('time', INTERVAL '7 days'), if_not_exists => TRUE, migrate_data => TRUE);

ALTER TABLE mediciones SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'variable, fuente',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('mediciones', INTERVAL '30 days', if_not_exists => TRUE);

-- Promedio, minimo y maximo por minuto: base para consultas rapidas del servidor MCP y Grafana.
CREATE MATERIALIZED VIEW IF NOT EXISTS mediciones_1min
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', time) AS minuto,
       variable,
       fuente,
       avg(valor) AS promedio,
       min(valor) AS minimo,
       max(valor) AS maximo,
       count(*)   AS muestras
FROM mediciones
GROUP BY minuto, variable, fuente
WITH NO DATA;

SELECT add_continuous_aggregate_policy('mediciones_1min',
    start_offset => INTERVAL '2 hours',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);
