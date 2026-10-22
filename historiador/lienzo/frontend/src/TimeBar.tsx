import { useEffect, useMemo, useState } from 'react';
import { fmtHora, isoLima } from './api';
import { IcoPausa, IcoPlay } from './icons';
import type { EventoLinea } from './types';

interface Props {
  momento: string | null;
  desde: number;
  hasta: number;
  eventos: EventoLinea[];
  /** variable -> [clase si 1, texto si 1, clase si 0, texto si 0] (de equipos.json) */
  marcas: Record<string, [string, string, string, string]>;
  onCambio: (m: string | null) => void;
}

export default function TimeBar({ momento, desde, hasta, eventos, marcas: MARCAS, onCambio }: Props) {
  const marcaDe = (variable: string, v: number): [string, string] => {
    const m = MARCAS[variable];
    if (!m) return ['modo', variable];
    return v ? [m[0], m[1]] : [m[2], m[3]];
  };
  const [jugando, setJugando] = useState(false);
  const [vel, setVel] = useState(20);
  const actual = momento ? Date.parse(momento) : hasta;
  const pos = (t: number) => `${((t - desde) / Math.max(1, hasta - desde)) * 100}%`;

  useEffect(() => {
    if (!jugando || !momento) return;
    const id = window.setInterval(() => {
      const sig = Date.parse(momento) + vel * 500;
      if (sig >= Date.now() - 2000) { setJugando(false); onCambio(null); } else onCambio(isoLima(sig));
    }, 500);
    return () => window.clearInterval(id);
  }, [jugando, momento, vel, onCambio]);

  const marcas = useMemo(() => eventos.filter((e) => Date.parse(e.t) >= desde && Date.parse(e.t) <= hasta), [eventos, desde, hasta]);

  return (
    <div className={`timebar ${momento ? 'hist' : 'vivo'}`}>
      <button className="tb-play" onClick={() => {
        if (!momento) { onCambio(isoLima(hasta - 10 * 60e3)); setJugando(true); } else setJugando(!jugando);
      }} aria-label={jugando ? 'Pausar' : 'Reproducir'}>{jugando ? <IcoPausa /> : <IcoPlay />}</button>
      <select value={vel} onChange={(e) => setVel(Number(e.target.value))} aria-label="Velocidad de reproducción">
        <option value={5}>×5</option><option value={20}>×20</option><option value={60}>×60</option>
      </select>
      <div className="tb-pista">
        <div className="tb-marcas">
          {marcas.map((e, i) => {
            const [cls, txt] = marcaDe(e.variable, e.valor);
            return (
              <button key={i} className={`tb-marca ${cls}`} style={{ left: pos(Date.parse(e.t)) }}
                title={`${fmtHora(e.t)} · ${txt}`} onClick={() => { setJugando(false); onCambio(e.t); }} />
            );
          })}
        </div>
        <input type="range" min={desde} max={hasta} step={1000} value={actual}
          onChange={(e) => { setJugando(false); const v = Number(e.target.value); onCambio(v >= hasta - 3000 ? null : isoLima(v)); }}
          aria-label="Momento del historial" />
        <div className="tb-escala"><span>{fmtHora(isoLima(desde))}</span><span>{fmtHora(isoLima(hasta))}</span></div>
      </div>
      <div className="tb-hora">
        <small>{momento ? 'Reproduciendo' : 'Tiempo real'}</small>
        <b>{momento ? fmtHora(momento) : fmtHora(isoLima(Date.now()))}</b>
      </div>
      <button className={`tb-vivo ${momento ? '' : 'on'}`} onClick={() => { setJugando(false); onCambio(null); }}>
        <span className="punto" />EN VIVO
      </button>
    </div>
  );
}
