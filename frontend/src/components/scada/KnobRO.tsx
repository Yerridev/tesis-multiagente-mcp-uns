import { useEffect, useRef, useState } from 'react';
import { num } from '../../utils/format';

/**
 * Perilla de SOLO LECTURA (porte de los BOSOTOs scada-antiguo-*).
 * No captura puntero ni teclado: es indicación pura, jamás escribe al PLC.
 */
export function KnobRO({ value, max, ticks, label, onCommit }: { value: number | null; max: number; ticks: number[]; label: string; onCommit?: (value: number) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [draft, setDraft] = useState<number | null>(value);
  const [dragging, setDragging] = useState(false);
  // Sincroniza con el PLC solo cuando LLEGA una lectura nueva. Al soltar la perilla no se
  // vuelve a pintar la lectura vieja: se mantiene el valor elegido hasta que el PLC confirme.
  const ultimoValor = useRef<number | null>(value);
  useEffect(() => {
    if (value === ultimoValor.current) return;
    ultimoValor.current = value;
    if (!dragging) setDraft(value);
  }, [value, dragging]);
  const SWEEP = 270;
  const toAngle = (v: number) => -SWEEP / 2 + (v / max) * SWEEP;
  const pt = (a: number, r: number): [number, number] => {
    const rad = ((a - 90) * Math.PI) / 180;
    return [100 + r * Math.cos(rad), 100 + r * Math.sin(rad)];
  };
  const clamp = (n: number) => Math.max(0, Math.min(max, n));
  const v = clamp(draft ?? 0);
  const [nx, ny] = pt(toAngle(v), 52);

  const desdePuntero = (clientX: number, clientY: number) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return v;
    const x = clientX - (box.left + box.width / 2);
    const y = clientY - (box.top + box.height / 2);
    let angle = Math.atan2(y, x) * 180 / Math.PI + 90;
    while (angle > 180) angle -= 360;
    while (angle < -180) angle += 360;
    return Math.round(clamp(((Math.max(-135, Math.min(135, angle)) + 135) / SWEEP) * max));
  };

  const terminar = (clientX: number, clientY: number) => {
    if (!onCommit) return;
    const nuevo = desdePuntero(clientX, clientY);
    setDraft(nuevo);
    setDragging(false);
    onCommit(nuevo);
  };
  return (
    <div className="ca-knob-wrap">
      <svg
        ref={svgRef}
        viewBox="0 0 200 200"
        className="ca-knob"
        role={onCommit ? 'slider' : 'img'}
        tabIndex={onCommit ? 0 : undefined}
        aria-valuemin={onCommit ? 0 : undefined}
        aria-valuemax={onCommit ? max : undefined}
        aria-valuenow={onCommit ? v : undefined}
        aria-label={`${label}: ${draft == null ? 'sin datos' : num(v, 1)}`}
        style={{ cursor: onCommit ? 'grab' : undefined }}
        onPointerDown={(e) => {
          if (!onCommit) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          setDragging(true);
          setDraft(desdePuntero(e.clientX, e.clientY));
        }}
        onPointerMove={(e) => { if (dragging && onCommit) setDraft(desdePuntero(e.clientX, e.clientY)); }}
        onPointerUp={(e) => terminar(e.clientX, e.clientY)}
        onKeyDown={(e) => {
          if (!onCommit || !['ArrowLeft', 'ArrowDown', 'ArrowRight', 'ArrowUp'].includes(e.key)) return;
          e.preventDefault();
          const nuevo = clamp(v + (e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 1 : -1));
          setDraft(nuevo);
          onCommit(nuevo);
        }}
      >
        {ticks.map((t) => {
          const [tx, ty] = pt(toAngle(t), 84);
          return <text key={t} x={tx} y={ty + 4} textAnchor="middle" className="ca-knob-tick">{t}</text>;
        })}
        <defs>
          <radialGradient id="ca-kb" cx="35%" cy="30%">
            <stop offset="0" stopColor="#4aa3ff" />
            <stop offset="1" stopColor="#0a3d8f" />
          </radialGradient>
        </defs>
        <circle cx="100" cy="100" r="62" fill="url(#ca-kb)" stroke="#0b2a5c" strokeWidth="3" opacity={draft == null ? 0.4 : 1} />
        <line x1="100" y1="100" x2={nx} y2={ny} stroke="#cfe6ff" strokeWidth="4" strokeLinecap="round" opacity={draft == null ? 0.3 : 1} />
      </svg>
      <span className={`ca-readout${draft == null ? ' nd' : ''}`}>{draft == null ? 'Sin dato' : num(v, 0)}</span>
      <small className="ca-knob-sub">{label}</small>
    </div>
  );
}
