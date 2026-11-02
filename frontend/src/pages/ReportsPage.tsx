import { useMemo } from 'react';
import { usePlant } from '../context/PlantContext';
import { EmptyBlock, ErrorBlock, LoadingBlock } from '../components/common/States';
import { IconBarChart } from '../components/common/Icons';
import { moduleMeta, num } from '../utils/format';

interface Stat {
  id: string;
  unit: string;
  color: string;
  label: string;
  count: number;
  min: number;
  avg: number;
  max: number;
  current: number;
}

export function ReportsPage() {
  const { equipment, historyFor, load, error, reload } = usePlant();

  const stats: Stat[] = useMemo(
    () =>
      equipment.map((item) => {
        const values = historyFor(item.id).map((s) => s.value);
        const meta = moduleMeta(item.id);
        return {
          id: item.id,
          unit: item.unit,
          color: meta.color,
          label: meta.short,
          count: values.length,
          min: values.length ? Math.min(...values) : 0,
          avg: values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0,
          max: values.length ? Math.max(...values) : 0,
          current: item.value,
        };
      }),
    [equipment, historyFor],
  );

  if (load === 'loading') return <LoadingBlock />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  const globalMax = Math.max(...stats.map((s) => s.max), 1);
  const withData = stats.filter((s) => s.count > 0);

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>Reporte estadístico</h2>
          <span className="panel-sub">Resumen por módulo · calculado sobre el búfer /api/history</span>
        </div>

        {withData.length === 0 ? (
          <EmptyBlock icon={<IconBarChart />} title="Sin muestras todavía" message="En cuanto llegue telemetría aparecerá el resumen." />
        ) : (
          <div className="rep-grid">
            {stats.map((stat) => (
              <article className="rep-card" key={stat.id}>
                <h3>
                  <span className="mod-dot" style={{ background: stat.color }} /> {stat.label}
                </h3>
                {stat.count === 0 ? (
                  <div className="rep-row">
                    <span>Sin datos</span>
                  </div>
                ) : (
                  <>
                    <div className="rep-row">
                      <span>Actual</span>
                      <b>
                        {num(stat.current, 2)} {stat.unit}
                      </b>
                    </div>
                    <div className="rep-row">
                      <span>Mínimo</span>
                      <b>{num(stat.min, 2)}</b>
                    </div>
                    <div className="rep-row">
                      <span>Promedio</span>
                      <b>{num(stat.avg, 2)}</b>
                    </div>
                    <div className="rep-row">
                      <span>Máximo</span>
                      <b>{num(stat.max, 2)}</b>
                    </div>
                    <div className="rep-row">
                      <span>Muestras</span>
                      <b>{stat.count}</b>
                    </div>
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Comparativa (mín / prom / máx)</h2>
          <div className="rep-legend">
            <span>
              <i style={{ background: '#90caf9' }} /> Mínimo
            </span>
            <span>
              <i style={{ background: '#59e900' }} /> Promedio
            </span>
            <span>
              <i style={{ background: '#ffb74d' }} /> Máximo
            </span>
          </div>
        </div>

        {withData.length === 0 ? (
          <EmptyBlock icon={<IconBarChart />} title="Sin datos para comparar" />
        ) : (
          <div className="rep-bars">
            {stats
              .filter((s) => s.count > 0)
              .map((stat) => (
                <div className="rep-bar-row" key={stat.id}>
                  <span style={{ color: stat.color }}>
                    {stat.label} ({stat.unit})
                  </span>
                  <div className="rep-bars-track">
                    <div>
                      <i style={{ width: `${(stat.min / globalMax) * 100}%`, background: '#90caf9' }} />
                      <small>{num(stat.min, 2)}</small>
                    </div>
                    <div>
                      <i style={{ width: `${(stat.avg / globalMax) * 100}%`, background: '#59e900' }} />
                      <small>{num(stat.avg, 2)}</small>
                    </div>
                    <div>
                      <i style={{ width: `${(stat.max / globalMax) * 100}%`, background: '#ffb74d' }} />
                      <small>{num(stat.max, 2)}</small>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        )}
        <p className="panel-sub" style={{ marginTop: 12 }}>
          Cada barra se escala contra el máximo global ({num(globalMax, 2)}); las unidades difieren entre módulos.
        </p>
      </section>
    </>
  );
}
