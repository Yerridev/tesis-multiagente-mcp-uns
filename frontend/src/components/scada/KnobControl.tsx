import type { PointerEvent as ReactPointerEvent } from 'react';
import { num } from '../../utils/format';

interface Props {
  value: number;
  min?: number;
  max: number;
  step?: number;
  ticks: number[];
  label: string;
  disabled?: boolean;
  onChange: (value: number) => void;
  onCommit?: (value: number) => void;
  /** El número bajo la perilla se puede escribir directamente (azul, letra blanca). */
  editable?: boolean;
}

export function KnobControl({ value, min = 0, max, step = 1, ticks, label, disabled, onChange, onCommit, editable }: Props) {
  const sweep = 270;
  const bounded = Math.max(min, Math.min(max, value));
  const angle = -sweep / 2 + ((bounded - min) / (max - min)) * sweep;
  const point = (a: number, radius: number): [number, number] => {
    const rad = ((a - 90) * Math.PI) / 180;
    return [100 + radius * Math.cos(rad), 100 + radius * Math.sin(rad)];
  };
  const [nx, ny] = point(angle, 52);

  const update = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (disabled) return bounded;
    const box = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - (box.left + box.width / 2);
    const y = e.clientY - (box.top + box.height / 2);
    let a = Math.atan2(y, x) * 180 / Math.PI + 90;
    if (a > 180) a -= 360;
    a = Math.max(-135, Math.min(135, a));
    const raw = min + ((a + 135) / 270) * (max - min);
    const next = Math.max(min, Math.min(max, Math.round(raw / step) * step));
    onChange(next);
    return next;
  };

  return (
    <div className={`ca-knob-wrap ca-knob-control${disabled ? ' disabled' : ''}`}>
      <svg viewBox="0 0 200 200" className="ca-knob" role="slider" tabIndex={disabled ? -1 : 0}
        aria-label={label} aria-valuemin={min} aria-valuemax={max} aria-valuenow={bounded}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); update(e); }}
        onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) update(e); }}
        onPointerUp={(e) => { const next = update(e); onCommit?.(next); }}
        onKeyDown={(e) => {
          if (disabled) return;
          if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
            const next = Math.min(max, bounded + step); onChange(next); onCommit?.(next);
          }
          if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
            const next = Math.max(min, bounded - step); onChange(next); onCommit?.(next);
          }
        }}>
        {ticks.map((t) => { const [x, y] = point(-135 + ((t - min) / (max - min)) * 270, 84); return <text key={t} x={x} y={y + 4} textAnchor="middle" className="ca-knob-tick">{t}</text>; })}
        <defs><radialGradient id={`knob-${max}`} cx="35%" cy="30%"><stop offset="0" stopColor="#4aa3ff" /><stop offset="1" stopColor="#0a3d8f" /></radialGradient></defs>
        <circle cx="100" cy="100" r="62" fill={`url(#knob-${max})`} stroke="#0b2a5c" strokeWidth="3" />
        <line x1="100" y1="100" x2={nx} y2={ny} stroke="#cfe6ff" strokeWidth="4" strokeLinecap="round" />
      </svg>
      {editable
        ? <input type="number" className="ca-readout ca-readout--edit" min={min} max={max} step={step} value={value}
            aria-label={label}
            onChange={(e) => onChange(Number(e.target.value))}
            onBlur={() => { if (!disabled) onCommit?.(bounded); }}
            onKeyDown={(e) => { if (e.key === 'Enter') { (e.target as HTMLInputElement).blur(); } }} />
        : <span className="ca-readout">{num(bounded, 0)}</span>}<small className="ca-knob-sub">{label}</small>
    </div>
  );
}
