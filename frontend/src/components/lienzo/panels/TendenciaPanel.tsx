import { useMemo, useState } from 'react';
import { usePlant } from '../../../context/PlantContext';
import { TrendChart, type ChartSeries } from '../../charts/TrendChart';
import { moduleMeta, timeOnly } from '../../../utils/format';

interface Props {
  ids: string[];
  unit: string;
  /** Momento histórico (epoch ms) o null = en vivo */
  momento: number | null;
}

const VENTANAS = [5, 15, 30];

/** Tendencia dentro del lienzo: mismos botones de ventana que el panel de la tesis. */
export function TendenciaPanel({ ids, unit, momento }: Props) {
  const { historyFor } = usePlant();
  const [ventana, setVentana] = useState(15);

  const series: ChartSeries[] = useMemo(() => {
    const t1 = momento ?? Date.now();
    const t0 = t1 - ventana * 60000;
    return ids.map((id) => ({
      id,
      label: moduleMeta(id).short,
      color: moduleMeta(id).color,
      fill: ids.length === 1,
      dashed: false,
      points: historyFor(id)
        .map((s) => ({ t: Date.parse(s.ts), v: s.value }))
        .filter((p) => p.t >= t0 && p.t <= t1),
    }));
  }, [ids, historyFor, momento, ventana]);

  const conDatos = series.some((s) => s.points.length > 1);
  const ultimo = series[0]?.points[series[0].points.length - 1];

  return (
    <div className="lz-tend">
      <div className="lz-tend-barra">
        {VENTANAS.map((m) => (
          <button key={m} type="button" className={m === ventana ? 'on' : ''} onClick={() => setVentana(m)}>
            {m} min
          </button>
        ))}
        <span className="lz-tend-nota">
          {momento
            ? `centrado en ${timeOnly(momento)}`
            : ultimo
              ? `últimos ${ventana} min · actualiza en vivo`
              : 'sin muestras en la ventana'}
        </span>
      </div>
      {conDatos ? (
        <TrendChart series={series} size="short" unit={unit} emptyText="Sin muestras en la ventana" />
      ) : (
        <div className="lz-vacio">Sin muestras en la ventana seleccionada</div>
      )}
    </div>
  );
}
