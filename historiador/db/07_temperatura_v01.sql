-- Migracion modulo de temperatura MCT-09/001 v0.1 (23-oct-2026). Ejecutar UNA vez:
--   Get-Content db\07_temperatura_v01.sql | docker exec -i uns-timescaledb psql -U uns_admin -d uns
-- (iniciar_arquitectura.ps1 la aplica sola si no encuentra el rango de temperatura/principal_c)
--
-- 1) Registra el rango de operacion del fabricante (manual Inducontrol MCT-09/001: 15-50 C) para la temperatura
--    del tanque principal y para el setpoint.
-- 2) Las variables nuevas no necesitan tablas: el ingestor-temperatura (VAR_PREFIX=temperatura-mct09/) las crea
--    al recibir el catalogo descriptivo/variables del conector.

BEGIN;

INSERT INTO rangos_validados (variable, minimo, maximo, unidad, validado_por, nota)
VALUES
  ('temperatura-mct09/temperatura/principal_c', 15, 50, 'C', 'FABRICANTE (manual Inducontrol MCT-09/001)',
   'Rango de operacion optimo del manual (apendice A2 y seccion 3.2.2). Escala raw*100/4095 tomada del SCADA original; '
   'falta contraste con termometro y validacion del responsable del laboratorio'),
  ('temperatura-mct09/pid/setpoint_c', 15, 50, 'C', 'FABRICANTE (manual Inducontrol MCT-09/001)',
   'El HMI original limita el setpoint a 0-50 C; el manual recomienda trabajar entre 15 y 50 C')
ON CONFLICT (variable) DO UPDATE SET minimo = EXCLUDED.minimo, maximo = EXCLUDED.maximo, unidad = EXCLUDED.unidad,
  validado_por = EXCLUDED.validado_por, nota = EXCLUDED.nota, actualizado = now();

COMMIT;

CALL refresh_continuous_aggregate('mediciones_1min', NULL, NULL);
