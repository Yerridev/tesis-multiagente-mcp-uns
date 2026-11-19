-- Migracion modulo de nivel v0.2 (20-oct-2026). Ejecutar UNA vez:
--   Get-Content db\05_nivel_v02.sql | docker exec -i uns-timescaledb psql -U uns_admin -d uns
--
-- 1) Renombra las variables publicadas por el conector v0.1 a los nombres confirmados en v0.2.
-- 2) Recalcula nivel/cm, nivel/pct y nivel/fuera_rango_sensor sobre todo el nivel/raw ya guardado
--    (calibracion 20-oct-2026: cm = (16348 - N7:4) / 400). Sin mediana: los picos de eco quedan en el historico.
-- 3) Registra el rango de trabajo del fabricante (0-35 cm) para nivel/cm.

BEGIN;

-- 1) Renombrar (se borran antes los duplicados exactos para no chocar con la restriccion UNIQUE)
CREATE TEMP TABLE renombres (viejo TEXT, nuevo TEXT) ON COMMIT DROP;
INSERT INTO renombres VALUES
  ('nivel-mcn09/bomba/velocidad_raw', 'nivel-mcn09/bomba/potenciometro_raw'),
  ('nivel-mcn09/estado/selector_a',   'nivel-mcn09/estado/selector_remoto'),
  ('nivel-mcn09/estado/selector_b',   'nivel-mcn09/estado/selector_local'),
  ('nivel-mcn09/estado/entrada_2',    'nivel-mcn09/estado/tanque1_con_agua');

DELETE FROM mediciones m USING renombres r
WHERE m.variable = r.viejo
  AND EXISTS (SELECT 1 FROM mediciones n WHERE n.variable = r.nuevo AND n.fuente = m.fuente AND n.time = m.time);

UPDATE mediciones m SET variable = r.nuevo FROM renombres r WHERE m.variable = r.viejo;
DELETE FROM variables v USING renombres r WHERE v.variable = r.viejo;

-- 2) Recalcular nivel calibrado sobre los datos crudos existentes
INSERT INTO mediciones (time, variable, valor, unidad, fuente, direccion)
SELECT time, 'nivel-mcn09/nivel/cm', round(((16348 - valor) / 400.0)::numeric, 1), 'cm', fuente, 'N7:4'
FROM mediciones WHERE variable = 'nivel-mcn09/nivel/raw'
ON CONFLICT DO NOTHING;

INSERT INTO mediciones (time, variable, valor, unidad, fuente, direccion)
SELECT time, 'nivel-mcn09/nivel/pct', round((100 * ((16348 - valor) / 400.0) / 60.0)::numeric, 1), '%', fuente, 'N7:4'
FROM mediciones WHERE variable = 'nivel-mcn09/nivel/raw'
ON CONFLICT DO NOTHING;

INSERT INTO mediciones (time, variable, valor, unidad, fuente, direccion)
SELECT time, 'nivel-mcn09/nivel/fuera_rango_sensor', CASE WHEN valor < 300 THEN 1 ELSE 0 END, NULL, fuente, 'N7:4'
FROM mediciones WHERE variable = 'nivel-mcn09/nivel/raw'
ON CONFLICT DO NOTHING;

-- 3) Rango de trabajo segun el manual Inducontrol MCN-09/001 (p. 11 y 13)
INSERT INTO rangos_validados (variable, minimo, maximo, unidad, validado_por, nota)
VALUES ('nivel-mcn09/nivel/cm', 0, 35, 'cm', 'FABRICANTE (manual Inducontrol MCN-09/001)',
        'Rango de trabajo del manual; el sensor satura cerca de 40 cm. Falta validacion del responsable del laboratorio')
ON CONFLICT (variable) DO UPDATE SET minimo = EXCLUDED.minimo, maximo = EXCLUDED.maximo, unidad = EXCLUDED.unidad,
  validado_por = EXCLUDED.validado_por, nota = EXCLUDED.nota, actualizado = now();

COMMIT;

CALL refresh_continuous_aggregate('mediciones_1min', NULL, NULL);
