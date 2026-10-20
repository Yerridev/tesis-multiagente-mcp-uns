-- Migracion v3.2 (19-oct-2026). Ejecutar UNA vez sobre una base ya creada:
--   docker exec -i uns-timescaledb psql -U uns_admin -d uns < db/04_migracion_v32.sql
-- En bases nuevas no hace falta (01_init.sql ya trae lo nuevo).
--
-- Motivo: en la tabla del lazo PID del S7-200 (VB159) los offsets 20 y 24 son Ti y Td (tiempos en minutos),
-- no ganancias Ki/Kd. VD100 se copia a Kc (VD171).

BEGIN;
UPDATE mediciones SET variable = 'pid/kc'                 WHERE variable = 'pid/kp';
UPDATE mediciones SET variable = 'pid/ti', unidad = 'min' WHERE variable = 'pid/ki';
UPDATE mediciones SET variable = 'pid/td', unidad = 'min' WHERE variable = 'pid/kd';
DELETE FROM variables WHERE variable IN ('pid/kp', 'pid/ki', 'pid/kd', 'caudal/actual',
                                         'actuadores/variador', 'actuadores/valvula_proporcional');

-- MW2 se publicaba siempre; en modo REMOTO su valor era el byte alto de AIW0 (no el potenciometro).
DELETE FROM mediciones m
WHERE m.variable = 'actuadores/potenciometro' AND m.fuente = 'uns'
  AND EXISTS (SELECT 1 FROM mediciones r
              WHERE r.variable = 'estado/selector_remoto' AND r.fuente = 'uns' AND r.valor = 1
                AND r.time = (SELECT max(time) FROM mediciones x
                              WHERE x.variable = 'estado/selector_remoto' AND x.fuente = 'uns' AND x.time <= m.time));

INSERT INTO rangos_validados (variable, minimo, maximo, unidad, validado_por, nota)
VALUES ('caudal/caudalimetro', 0, 141, 'L/min', 'PENDIENTE', 'Rango de calibracion del Kobold DRG; falta rango operativo validado')
ON CONFLICT (variable) DO NOTHING;
COMMIT;

-- Recalcular el agregado por minuto con los nombres nuevos
CALL refresh_continuous_aggregate('mediciones_1min', NULL, NULL);
