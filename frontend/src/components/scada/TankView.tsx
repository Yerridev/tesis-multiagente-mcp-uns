import { clamp, num } from '../../utils/format';

interface Props {
  value: number;
  unit: string;
  setpoint: number;
  tankHeight: number;
  percent: number;
  high: boolean;
  low: boolean;
  /** Sin lectura real del PLC: no se presentan valores. */
  sinDato?: boolean;
}

const SHELL = { x: 78, y: 34, w: 104, h: 206 };
const BOTTOM = SHELL.y + SHELL.h;

/** Representación visual del tanque MCN-09 (solo lectura, sin comandos). */
export function TankView({ value, unit, setpoint, tankHeight, percent, high, low, sinDato }: Props) {
  const pct = clamp(percent);
  const fillH = (SHELL.h * pct) / 100;
  const fillY = BOTTOM - fillH;
  const surfaceY = fillY;

  const yFor = (cm: number) => BOTTOM - SHELL.h * clamp((cm / tankHeight) * 100) / 100;
  /* Sin consigna real no se dibujan la consigna ni las bandas de alarma */
  const haySp = setpoint > 0;
  const spY = yFor(setpoint);
  const highY = yFor(setpoint * 1.15);
  const lowY = yFor(setpoint * 0.85);

  const ticks = Array.from({ length: 6 }, (_, i) => {
    const cm = (tankHeight / 5) * i;
    return { cm, y: yFor(cm) };
  });

  return (
    <div className="tank-wrap">
      <svg className="tank-svg" viewBox="0 0 260 300" role="img" aria-label={sinDato ? "Nivel del tanque sin datos" : `Nivel del tanque: ${num(value, 2)} ${unit}`}>
        <defs>
          <linearGradient id="tankGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#66bb6a" />
            <stop offset="100%" stopColor="#2e7d32" />
          </linearGradient>
        </defs>

        {/* carcasa (fondo) */}
        <rect className="tank-shell" x={SHELL.x} y={SHELL.y} width={SHELL.w} height={SHELL.h} rx="8" />

        {/* líquido */}
        <rect className="tank-fill" x={SHELL.x + 2} y={fillY} width={SHELL.w - 4} height={Math.max(fillH, 0)} />
        <line
          x1={SHELL.x + 2}
          y1={surfaceY}
          x2={SHELL.x + SHELL.w - 2}
          y2={surfaceY}
          stroke="#1b5e20"
          strokeWidth="2"
          opacity={pct > 1 ? 0.75 : 0}
        />

        {/* escala */}
        {ticks.map((tick) => (
          <g key={tick.cm}>
            <line
              className="tank-grid-line"
              x1={SHELL.x}
              y1={tick.y}
              x2={SHELL.x + SHELL.w}
              y2={tick.y}
              strokeDasharray="3 4"
            />
            <text className="tank-tick-label" x={SHELL.x - 12} y={tick.y + 3} textAnchor="end">
              {tick.cm.toFixed(0)}
            </text>
          </g>
        ))}
        <text className="tank-tick-label" x={SHELL.x - 12} y={SHELL.y - 10} textAnchor="end">
          {unit}
        </text>

        {/* consigna y límites de alarma (solo con consigna real) */}
        {haySp ? (
          <>
            <line className="tank-setpoint" x1={SHELL.x - 6} y1={spY} x2={SHELL.x + SHELL.w + 6} y2={spY} />
            <text x={SHELL.x + SHELL.w + 10} y={spY + 3} fill="#2e7d32" fontSize="9.5" fontWeight="700">
              SP {num(setpoint, 1)}
            </text>
            <line className="tank-limit" x1={SHELL.x} y1={highY} x2={SHELL.x + SHELL.w} y2={highY} />
            <text x={SHELL.x + SHELL.w + 10} y={highY + 3} fill="#c62828" fontSize="9" fontWeight="700">
              ALTA
            </text>
            <line className="tank-limit low" x1={SHELL.x} y1={lowY} x2={SHELL.x + SHELL.w} y2={lowY} />
            <text x={SHELL.x + SHELL.w + 10} y={lowY + 3} fill="#e65100" fontSize="9" fontWeight="700">
              BAJA
            </text>
          </>
        ) : null}

        {/* detalle superior / inferior */}
        <rect className="tank-cap" x={SHELL.x - 8} y={SHELL.y - 12} width={SHELL.w + 16} height="12" rx="4" />
        <rect className="tank-cap" x={SHELL.x + 8} y={BOTTOM} width={SHELL.w - 16} height="10" rx="3" />
        <rect
          className={`tank-alarm-ring${high || low ? ' on' : ''}`}
          x={SHELL.x - 4}
          y={SHELL.y - 4}
          width={SHELL.w + 8}
          height={SHELL.h + 8}
          rx="12"
        />

        {/* lectura */}
        <text className="tank-value" x={130} y={272}>
          {sinDato ? 'Sin datos' : `${num(value, 2)} ${unit}`}
        </text>
        <text className="tank-unit" x={130} y={287}>
          {sinDato ? 'sin lectura del PLC' : `nivel actual · ${num(pct, 1)} % del tanque`}
        </text>
      </svg>

      <div className="tank-legend">
        {haySp ? (
          <>
            <div>
              <span>
                <i />
                Consigna
              </span>
              <b>
                {num(setpoint, 2)} {unit}
              </b>
            </div>
            <div>
              <span>
                <i className="lim" />
                Alarma alta (≥ 115 %)
              </span>
              <b>
                {num(setpoint * 1.15, 2)} {unit}
              </b>
            </div>
            <div>
              <span>
                <i className="lim-low" />
                Alarma baja (≤ 85 %)
              </span>
              <b>
                {num(setpoint * 0.85, 2)} {unit}
              </b>
            </div>
          </>
        ) : (
          <div>
            <span>Consigna / alarmas</span>
            <b>Sin datos</b>
          </div>
        )}
        <div>
          <span>Capacidad del tanque</span>
          <b>{tankHeight > 0 ? `${num(tankHeight, 0)} ${unit}` : 'Sin datos'}</b>
        </div>
      </div>
    </div>
  );
}
