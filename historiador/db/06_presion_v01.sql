-- Migracion modulo de presion MCP-09/001 v0.1 (21-oct-2026). Ejecutar UNA vez:
--   Get-Content db\06_presion_v01.sql | docker exec -i uns-timescaledb psql -U uns_admin -d uns
--
-- 1) Renombra los selectores publicados por el conector v0.2 inicial a los nombres comunes de la arquitectura
--    (REMOTO = SEL_AUTO, LOCAL = SEL_MANUAL; confirmado en la prueba remota del 21-oct-2026 18:50).
-- 2) Registra el rango de trabajo del fabricante para la presion (manual Inducontrol MCP-09/001: 3-40 psi).
-- 3) Corrige unidades de la salida del PID y de la valvula (V) en las filas ya guardadas.

BEGIN;

-- Los datos de presion existen solo desde el 21-oct-2026; el filtro por tiempo evita descomprimir
-- los chunks historicos (.lvm 2008-2011). El SET LOCAL es un respaldo por si algun chunk reciente ya esta comprimido.
SET LOCAL timescaledb.max_tuples_decompressed_per_dml_transaction = 0;

CREATE TEMP TABLE renombres (viejo TEXT, nuevo TEXT) ON COMMIT DROP;
INSERT INTO renombres VALUES
  ('presion-mcp09/estado/selector_auto',   'presion-mcp09/estado/selector_remoto'),
  ('presion-mcp09/estado/selector_manual', 'presion-mcp09/estado/selector_local');

DELETE FROM mediciones m USING renombres r
WHERE m.time >= '2026-10-21' AND m.variable = r.viejo
  AND EXISTS (SELECT 1 FROM mediciones n WHERE n.time >= '2026-10-21' AND n.variable = r.nuevo
              AND n.fuente = m.fuente AND n.time = m.time);

UPDATE mediciones m SET variable = r.nuevo FROM renombres r
WHERE m.time >= '2026-10-21' AND m.variable = r.viejo;
DELETE FROM variables v USING renombres r WHERE v.variable = r.viejo;

UPDATE mediciones SET unidad = 'V'
WHERE time >= '2026-10-21' AND variable IN ('presion-mcp09/pid/cv', 'presion-mcp09/pid/valvula_pc') AND unidad IS DISTINCT FROM 'V';

INSERT INTO rangos_validados (variable, minimo, maximo, unidad, validado_por, nota)
VALUES ('presion-mcp09/presion/psi', 3, 40, 'psi', 'FABRICANTE (manual Inducontrol MCP-09/001)',
        'Rango de operacion del manual (5-40 psi en A2, 3-40 psi recomendado con la valvula al 30 %). '
        'Escala (mA-4)/16*87 validada contra la HMI el 21-oct-2026 (manometro averiado). '
        'Falta validacion del responsable del laboratorio')
ON CONFLICT (variable) DO UPDATE SET minimo = EXCLUDED.minimo, maximo = EXCLUDED.maximo, unidad = EXCLUDED.unidad,
  validado_por = EXCLUDED.validado_por, nota = EXCLUDED.nota, actualizado = now();

COMMIT;

CALL refresh_continuous_aggregate('mediciones_1min', NULL, NULL);
