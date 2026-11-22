interface Props {
  points: { t: number; v: number }[];
  color: string;
  height?: number;
}

/** Mini-gráfico de tendencia sin dependencias (SVG con escala no uniforme). */
export function Sparkline({ points, color, height = 46 }: Props) {
  if (points.length < 2) {
    return (
      <div className="eq-spark" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" width="100%" height="100%" aria-hidden="true">
          <line
            x1="0"
            y1="50"
            x2="100"
            y2="50"
            stroke="#e0e0e0"
            strokeWidth="1"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
    );
  }

  const values = points.map((p) => p.v);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = span * 0.15;
  const lo = min - pad;
  const hi = max + pad;

  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * 100;
    const y = 100 - ((p.v - lo) / (hi - lo)) * 100;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return (
    <div className="eq-spark" style={{ height }}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" width="100%" height="100%" aria-hidden="true">
        <polygon points={`0,100 ${coords.join(' ')} 100,100`} fill={color} opacity="0.13" />
        <polyline
          points={coords.join(' ')}
          fill="none"
          stroke={color}
          strokeWidth="1.8"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}
