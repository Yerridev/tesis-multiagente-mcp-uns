import { useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { num, timeOnly } from '../../utils/format';

export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  points: { t: number; v: number }[];
  dashed?: boolean;
  fill?: boolean;
}

interface Props {
  series: ChartSeries[];
  unit?: string;
  size?: 'short' | 'normal' | 'tall';
  showLegend?: boolean;
  emptyText?: string;
  /** Escala fija del eje Y (como los SCADA originales): ej. [0,10,...,60]. Sin esto se auto-escala. */
  yTicks?: number[];
  /** Título «Tiempo» centrado bajo el eje X (fiel al SCADA original). */
  timeTitle?: boolean;
}

interface Hover {
  x: number;
  index: number;
  t: number;
}

const X_MARKS = 6; // marcas de tiempo en el eje X (como el SCADA original)

/**
 * Gráfico de líneas SVG sin dependencias.
 * Con `yTicks` usa escala fija con marcas alineadas; el eje X muestra
 * marcas de hora evenly distribuidas y, con `timeTitle`, el rótulo «Tiempo».
 */
export function TrendChart({
  series,
  unit,
  size = 'normal',
  showLegend = true,
  emptyText = 'Aún no hay muestras para graficar',
  yTicks,
  timeTitle = false,
}: Props) {
  const [hover, setHover] = useState<Hover | null>(null);

  const longest = useMemo(
    () => series.reduce<ChartSeries | null>((best, s) => (!best || s.points.length > best.points.length ? s : best), null),
    [series],
  );
  const count = longest?.points.length ?? 0;

  const scale = useMemo(() => {
    const values = series.flatMap((s) => s.points.map((p) => p.v));

    if (yTicks && yTicks.length > 1) {
      const step = Math.abs(yTicks[1] - yTicks[0]) || 1;
      const lo = Math.min(...yTicks);
      let hi = Math.max(...yTicks);
      const maxData = values.length ? Math.max(...values) : Number.NEGATIVE_INFINITY;
      while (maxData > hi) hi = Math.round((hi + step) * 1000) / 1000; // la escala crece si el dato se sale
      const ticks: number[] = [];
      for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v * 1000) / 1000);
      const decimals = step < 1 ? 1 : 0;
      return { lo, hi, ticks, decimals };
    }

    if (values.length === 0) return { lo: 0, hi: 1, ticks: [0, 0.5, 1], decimals: 1 };
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || Math.abs(max) * 0.1 || 1;
    const pad = span * 0.15;
    const lo = min - pad;
    const hi = max + pad;
    return { lo, hi, ticks: [lo, (lo + hi) / 2, hi], decimals: 1 };
  }, [series, yTicks]);

  const pctY = (v: number) => 100 - ((v - scale.lo) / (scale.hi - scale.lo || 1)) * 100;

  const toPath = (points: { t: number; v: number }[]) => {
    const span = scale.hi - scale.lo || 1;
    const n = Math.max(points.length - 1, 1);
    return points
      .map((p, i) => {
        const x = (i / n) * 100;
        const y = 100 - ((p.v - scale.lo) / span) * 100;
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(' ');
  };

  const areaPath = (points: { t: number; v: number }[]) =>
    points.length > 1 ? `${toPath(points)} L100 100 L0 100 Z` : '';

  const onMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!longest || count < 2) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const rel = (event.clientX - rect.left) / rect.width;
    const index = Math.min(count - 1, Math.max(0, Math.round(rel * (count - 1))));
    setHover({
      x: Math.min(93, Math.max(7, rel * 100)),
      index,
      t: longest.points[index]?.t ?? Date.now(),
    });
  };

  const empty = count < 2;
  const first = longest?.points[0]?.t;
  const last = longest?.points[count - 1]?.t;

  // Marcas del eje X: horas repartidas entre la primera y la última muestra.
  // Sin datos se muestra igual la ventana de tiempo (como el SCADA original): últimos 30 s.
  const xLabels = useMemo(() => {
    if (empty || first == null || last == null) return null;
    if (last === first) return [timeOnly(first)];
    return Array.from({ length: X_MARKS }, (_, i) => timeOnly(first + ((last - first) * i) / (X_MARKS - 1)));
  }, [empty, first, last]);
  const xLabelsVacia = Array.from({ length: X_MARKS }, (_, i) =>
    timeOnly(Date.now() - 30_000 + (30_000 * i) / (X_MARKS - 1)),
  );
  const etiquetas = xLabels ?? xLabelsVacia;
  const xPositions = Array.from({ length: X_MARKS }, (_, i) => (i / (X_MARKS - 1)) * 100);

  const valueAt = (s: ChartSeries) => {
    if (!s.points.length) return null;
    const idx = count > 1 ? Math.round((hover!.index / (count - 1)) * (s.points.length - 1)) : 0;
    return s.points[Math.min(s.points.length - 1, Math.max(0, idx))];
  };

  return (
    <div>
      {showLegend ? (
        <div className="chart-legend" style={{ marginBottom: 8 }}>
          {series.map((s) => (
            <span key={s.id} style={{ color: s.color }}>
              <i style={{ borderTopStyle: s.dashed ? 'dashed' : 'solid' }} />
              <span style={{ color: 'var(--muted)' }}>{s.label}</span>
            </span>
          ))}
        </div>
      ) : null}

      <div className={`chart${size === 'tall' ? ' tall' : size === 'short' ? ' short' : ''}`}>
        <div className="chart-y" aria-hidden="true">
          {unit ? <span className="chart-unit">{unit}</span> : null}
          {[...scale.ticks].reverse().map((v, i) => (
            <span key={`${v}-${i}`}>{num(v, scale.decimals)}</span>
          ))}
        </div>

        <div className="chart-plot" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {scale.ticks.map((v) => (
              <line key={`h${v}`} x1="0" y1={pctY(v)} x2="100" y2={pctY(v)} stroke="currentColor" className="chart-grid" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            ))}
            {xPositions.map((x) => (
              <line key={`v${x}`} x1={x} y1="0" x2={x} y2="100" stroke="currentColor" className="chart-grid" strokeWidth="1" vectorEffect="non-scaling-stroke" />
            ))}
            {!empty
              ? series.map((s) => (
                  <g key={s.id}>
                    {s.fill && s.points.length > 1 ? (
                      <path d={areaPath(s.points)} fill={s.color} opacity="0.12" />
                    ) : null}
                    <path
                      d={toPath(s.points)}
                      fill="none"
                      stroke={s.color}
                      strokeWidth={s.dashed ? 1.8 : 2.2}
                      strokeDasharray={s.dashed ? '7 5' : undefined}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      vectorEffect="non-scaling-stroke"
                    />
                  </g>
                ))
              : null}
            {hover && !empty ? (
              <line
                x1={(hover.index / Math.max(count - 1, 1)) * 100}
                y1="0"
                x2={(hover.index / Math.max(count - 1, 1)) * 100}
                y2="100"
                stroke="#9e9e9e"
                strokeWidth="1"
                strokeDasharray="3 3"
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
          </svg>

          {empty ? <div className="chart-empty">{emptyText}</div> : null}

          {hover && !empty ? (
            <div className="chart-tip" style={{ left: `${hover.x}%` }}>
              <div>{timeOnly(hover.t)}</div>
              {series.map((s) => {
                const p = valueAt(s);
                return (
                  <div key={s.id}>
                    <span style={{ color: s.color }}>●</span> {s.label}:{' '}
                    <b>{p ? num(p.v, 2) : '—'}</b> {unit ?? ''}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>

        <div className="chart-x" aria-hidden="true">
          {etiquetas.map((l, i) => (
            <span key={`${l}-${i}`}>{l}</span>
          ))}
        </div>

        {timeTitle ? <div className="chart-x-title">Tiempo</div> : null}
      </div>
    </div>
  );
}
