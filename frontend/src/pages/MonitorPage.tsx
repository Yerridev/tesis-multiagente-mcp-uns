import { useMemo } from 'react';
import { usePlant } from '../context/PlantContext';
import { TrendChart, type ChartSeries } from '../components/charts/TrendChart';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { moduleMeta, num, valorMedible } from '../utils/format';

export function MonitorPage() {
  const { equipment, historyFor, link, load, error, reload } = usePlant();

  const series: ChartSeries[] = useMemo(
    () =>
      equipment.map((item) => ({
        id: item.id,
        label: `${moduleMeta(item.id).short} (${item.unit})`,
        color: moduleMeta(item.id).color,
        fill: true,
        points: historyFor(item.id)
          .slice(-240)
          .map((s) => ({ t: Date.parse(s.ts), v: s.value })),
      })),
    [equipment, historyFor],
  );

  const points = equipment.map((item) => historyFor(item.id).length);

  if (load === 'loading') return <LoadingBlock />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Monitoreo continuo</h2>
            <span className="panel-sub">
              Flujo en vivo · {Math.max(...points, 0)} puntos en el módulo con más muestras
            </span>
          </div>
          <span className={`pill ${link === 'connected' ? 'pill-ok pill-live' : 'pill-idle'}`}>
            <i />
            {link === 'connected' ? 'Recibiendo' : 'En pausa'}
          </span>
        </div>
        <TrendChart series={series} size="tall" emptyText="Esperando telemetría del canal SSE…" />
      </section>

      <section className="cards-live">
        {equipment.map((item) => (
          <div className={`live-box live-${item.id.split('-')[0]}`} key={item.id}>
            <span>{moduleMeta(item.id).short}</span>
            <b className={valorMedible(item.calidad) ? undefined : 'nodata'}>
              {valorMedible(item.calidad) ? num(item.value, 2) : 'n/d'}
            </b>
            <small>
              {item.unit} · consigna {num(item.setpoint, 1)} {item.unit} · {moduleMeta(item.id).label}
              {valorMedible(item.calidad) ? '' : ' · SIN MEDIDA (sensor fuera de rango)'}
            </small>
          </div>
        ))}
      </section>
    </>
  );
}
