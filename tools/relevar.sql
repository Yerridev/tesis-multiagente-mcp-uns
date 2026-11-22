\pset pager off
SELECT e.equipo, count(DISTINCT s.id) senales, count(m.*) filas, min(m.ts) desde, max(m.ts) hasta
FROM equipos e LEFT JOIN senales s ON s.equipo_id=e.id LEFT JOIN mediciones m ON m.senal_id=s.id GROUP BY 1 ORDER BY 1;
SELECT e.equipo, s.nombre, s.unidad, count(m.*) n, max(m.ts) ultimo, (array_agg(m.valor ORDER BY m.ts DESC))[1] ultimo_valor
FROM senales s JOIN equipos e ON e.id=s.equipo_id LEFT JOIN mediciones m ON m.senal_id=s.id GROUP BY 1,2,3 ORDER BY 1,2;
SELECT calidad, count(*) FROM mediciones GROUP BY 1;
SELECT rolname FROM pg_roles WHERE rolname IN ('ingestor','backend_ro','mcp_reader');
\dt
