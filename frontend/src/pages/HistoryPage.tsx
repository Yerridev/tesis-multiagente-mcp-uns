import { useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import type { Route } from '../router';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart, type ChartSeries } from '../components/charts/TrendChart';
import { IconHistory, IconRefresh } from '../components/common/Icons';
import { dateOnly, isAlarm, moduleMeta, num, timeOnly } from '../utils/format';

const RANGES = [
  { label: '5 min', minutes: 5 },
  { label: '15 min', minutes: 15 },
  { label: '1 h', minutes: 60 },
  { label: 'Todo', minutes: 0 },
];

interface Props {
  onNavigate: (route: Route) => void;
}

export function HistoryPage({ onNavigate }: Props) {
  const { equipment, history, load, error, now, reload } = usePlant();
  const [filterId, setFilterId] = useState('');
  const [minutes, setMinutes] = useState(15);

  const setpointOf = useMemo(() => {
    const map: Record<string, number> = {};
    for (const item of equipment) map[item.id] = item.setpoint;
    return map;
  }, [equipment]);

  const filtered = useMemo(() => {
    const min = minutes > 0 ? now - minutes * 60000 : 0;
    return history.filter((s) => {
      if (filterId && s.id !== filterId) return false;
      if (min && Date.parse(s.ts) < min) return false;
      return true;
    });
  }, [history, filterId, minutes, now]);

  const stats = useMemo(() => {
    if (!filtered.length) return null;
    const values = filtered.map((s) => s.value);
    return {
      count: filtered.length,
      min: Math.min(...values),
      avg: values.reduce((a, b) => a + b, 0) / values.length,
      max: Math.max(...values),
    };
  }, [filtered]);

  const series: ChartSeries[] = useMemo(() => {
    const ids = filterId ? [filterId] : equipment.map((e) => e.id);
    return ids.map((id) => {
      const unit = equipment.find((e) => e.id === id)?.unit ?? '';
      return {
        id,
        label: `${moduleMeta(id).short} (${unit})`,
        color: moduleMeta(id).color,
        fill: Boolean(filterId),
        points: filtered
          .filter((s) => s.id === id)
          .slice(-400)
          .map((s) => ({ t: Date.parse(s.ts), v: s.value })),
      };
    });
  }, [filtered, filterId, equipment]);

  const rows = useMemo(() => filtered.slice(-250).reverse(), [filtered]);

  if (load === 'loading') return <LoadingBlock label="Cargando histórico de mediciones…" />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  return (
    <>
      <div className="section-title">
        <div>
          <div className="eyebrow">Datos almacenados</div>
          <h2>Históricos de mediciones</h2>
          <p>Búfer de telemetría del backend (/api/history) ampliado en vivo por SSE.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={reload}>
          <IconRefresh width="15" height="15" /> Actualizar
        </button>
      </div>

      <section className="panel">
        <div className="panel-head">
          <div className="filters">
            <select className="select" value={filterId} onChange={(event) => setFilterId(event.target.value)}>
              <option value="">Todos los módulos</option>
              {equipment.map((item) => (
                <option key={item.id} value={item.id}>
                  {moduleMeta(item.id).label}
                </option>
              ))}
            </select>
            <span className="sep">·</span>
            {RANGES.map((range) => (
              <button
                key={range.label}
                type="button"
                className={`btn btn-ghost${minutes === range.minutes ? ' active' : ''}`}
                onClick={() => setMinutes(range.minutes)}
              >
                {range.label}
              </button>
            ))}
          </div>
          <span className="panel-sub">Rango en memoria: 30 min por equipo</span>
        </div>

        <div className="hist-stats" style={{ marginBottom: 14 }}>
          <span>
            Muestras: <b>{stats ? stats.count : 0}</b>
          </span>
          <span>
            Módulos: <b>{filterId ? 1 : equipment.length}</b>
          </span>
          {filterId && stats ? (
            <>
              <span>
                Mínimo: <b>{num(stats.min, 2)}</b>
              </span>
              <span>
                Promedio: <b>{num(stats.avg, 2)}</b>
              </span>
              <span>
                Máximo: <b>{num(stats.max, 2)}</b>
              </span>
            </>
          ) : (
            <span className="muted">Selecciona un módulo para ver mínimo, promedio y máximo en su unidad.</span>
          )}
        </div>

        {stats ? (
          <TrendChart series={series} size="normal" emptyText="Sin muestras en el rango seleccionado" />
        ) : (
          <EmptyBlock
            icon={<IconHistory />}
            title="Sin mediciones en el rango seleccionado"
            message="Amplía el rango o espera nuevas muestras del canal SSE."
          />
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Registro de muestras</h2>
          <span className="panel-sub">
            {rows.length} fila(s) · orden descendente · alarma calculada sobre la consigna del equipo
          </span>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Hora</th>
                <th>Módulo</th>
                <th>Variable</th>
                <th>Valor</th>
                <th>Unidad</th>
                <th>Alarma</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty">
                    Sin mediciones en el rango seleccionado.
                  </td>
                </tr>
              ) : (
                rows.map((sample, index) => {
                  const meta = moduleMeta(sample.id);
                  const setpoint = setpointOf[sample.id];
                  const alarm = setpoint === undefined ? false : isAlarm(sample.value, setpoint);
                  return (
                    <tr key={`${sample.ts}-${sample.id}-${index}`}>
                      <td>{dateOnly(sample.ts)}</td>
                      <td>{timeOnly(sample.ts)}</td>
                      <td style={{ color: meta.color, fontWeight: 700 }}>{meta.short}</td>
                      <td>{sample.variable}</td>
                      <td>
                        <b>{num(sample.value, 2)}</b>
                      </td>
                      <td>{sample.unit}</td>
                      <td>
                        <span className={`tag ${alarm ? 'tag-err' : 'tag-ok'}`}>{alarm ? 'Alarma' : 'Normal'}</span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <p className="panel-sub" style={{ marginTop: 10 }}>
          ¿Quieres ver el proceso en vivo?{' '}
          <button type="button" className="eq-link" onClick={() => onNavigate('nivel')}>
            Abrir el SCADA de nivel
          </button>
        </p>
      </section>
    </>
  );
}
