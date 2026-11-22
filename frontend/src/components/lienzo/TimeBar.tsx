import { useEffect, useState } from 'react';
import { IconPause, IconPlay } from '../common/Icons';
import { timeOnly } from '../../utils/format';

interface Props {
  momento: number | null;
  desde: number;
  hasta: number;
  onCambio: (momento: number | null) => void;
}

/** Barra de tiempo (versión del lienzo de la tesis) sobre el búfer de historial del backend. */
export function TimeBar({ momento, desde, hasta, onCambio }: Props) {
  const [jugando, setJugando] = useState(false);
  const [vel, setVel] = useState(20);
  const actual = momento ?? hasta;
  const pos = (t: number) => `${((t - desde) / Math.max(1, hasta - desde)) * 100}%`;

  useEffect(() => {
    if (!jugando || momento === null) return;
    const id = window.setInterval(() => {
      const sig = momento + vel * 500;
      if (sig >= Date.now() - 2000) {
        setJugando(false);
        onCambio(null);
      } else {
        onCambio(sig);
      }
    }, 500);
    return () => window.clearInterval(id);
  }, [jugando, momento, vel, onCambio]);

  const rango = Math.max(1, hasta - desde);

  return (
    <div className={`lz-timebar ${momento === null ? 'vivo' : 'hist'}`}>
      <button
        type="button"
        className="lz-tb-play"
        aria-label={jugando ? 'Pausar' : 'Reproducir'}
        onClick={() => {
          if (momento === null) {
            onCambio(hasta - 10 * 60000);
            setJugando(true);
          } else {
            setJugando((v) => !v);
          }
        }}
      >
        {jugando ? <IconPause width="16" height="16" /> : <IconPlay width="16" height="16" />}
      </button>

      <select
        value={vel}
        onChange={(event) => setVel(Number(event.target.value))}
        aria-label="Velocidad de reproducción"
        className="select"
      >
        <option value={5}>×5</option>
        <option value={20}>×20</option>
        <option value={60}>×60</option>
      </select>

      <div className="lz-tb-pista">
        <div className="lz-tb-marcas" aria-hidden="true">
          <span className="lz-tb-marca" style={{ left: '0%' }} />
          <span className="lz-tb-marca" style={{ left: '25%' }} />
          <span className="lz-tb-marca" style={{ left: '50%' }} />
          <span className="lz-tb-marca" style={{ left: '75%' }} />
          <span className="lz-tb-marca" style={{ left: 'calc(100% - 2px)' }} />
        </div>
        <input
          type="range"
          min={desde}
          max={hasta}
          step={1000}
          value={actual}
          onChange={(event) => {
            setJugando(false);
            const v = Number(event.target.value);
            onCambio(v >= hasta - 3000 ? null : v);
          }}
          aria-label="Momento del historial"
          style={{ background: `linear-gradient(90deg, var(--uss-green) ${pos(actual)}, #e0e0e0 ${pos(actual)})` }}
        />
        <div className="lz-tb-escala">
          <span>{timeOnly(desde)}</span>
          <span>{timeOnly(hasta)}</span>
        </div>
      </div>

      <div className="lz-tb-hora">
        <small>{momento === null ? 'Tiempo real' : 'Reproduciendo'}</small>
        <b>{timeOnly(actual)}</b>
      </div>

      <button
        type="button"
        className={`lz-tb-vivo${momento === null ? ' on' : ''}`}
        onClick={() => {
          setJugando(false);
          onCambio(null);
        }}
      >
        <span className="lz-punto" /> EN VIVO
      </button>
    </div>
  );
}
