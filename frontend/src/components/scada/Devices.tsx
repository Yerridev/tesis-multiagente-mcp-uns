import type { CSSProperties } from 'react';
import { num } from '../../utils/format';
import { IconLock } from '../common/Icons';

/* ---------- Bomba + variador ---------- */
export function PumpBlock({ on, hz, percent, available }: { on: boolean; hz: number | null; percent: number | null; available: boolean }) {
  return (
    <div className="dev-block">
      <div className="dev-head">
        <h3>Bomba de llenado · variador</h3>
        <span className={`pill ${!available ? 'pill-idle' : on ? 'pill-ok pill-live' : 'pill-idle'}`}>
          <i />
          {!available ? 'Sin datos' : on ? 'Encendida' : 'Detenida'}
        </span>
      </div>

      <div className="dev-figure">
        <svg width="86" height="72" viewBox="0 0 86 72" aria-hidden="true">
          <rect
            x="5"
            y="20"
            width="36"
            height="30"
            rx="5"
            fill={on ? '#e8f5e9' : '#eceff1'}
            stroke={on ? '#2e7d32' : '#90a4ae'}
            strokeWidth="2"
          />
          <circle
            cx="58"
            cy="35"
            r="17"
            fill={on ? '#e8f5e9' : '#eceff1'}
            stroke={on ? '#2e7d32' : '#90a4ae'}
            strokeWidth="2"
          />
          <path d="M58 35 L70 35" stroke={on ? '#2e7d32' : '#90a4ae'} strokeWidth="3" strokeLinecap="round" />
          <path
            d="M58 35 L66 28"
            stroke={on ? '#43a047' : '#b0bec5'}
            strokeWidth="3"
            strokeLinecap="round"
            style={{ transformOrigin: '58px 35px', animation: on ? 'spin 1.4s linear infinite' : undefined }}
          />
          <path d="M41 35 L46 35" stroke={on ? '#2e7d32' : '#90a4ae'} strokeWidth="3" strokeLinecap="round" />
          <rect x="5" y="55" width="76" height="6" rx="3" fill={on ? '#59e900' : '#e0e0e0'} opacity="0.65" />
        </svg>

        <div className="dev-rows">
          <div className="dev-row">
            <span>Estado</span>
            <b className={available ? undefined : 'nodata'}>{available ? (on ? 'ENCENDIDA' : 'APAGADA') : 'Sin datos'}</b>
          </div>
          <div className="dev-row">
            <span>Variador</span>
            <b className={available ? undefined : 'nodata'}>{available ? `${num(hz, 1)} Hz` : 'Sin datos'}</b>
          </div>
          <div className="dev-row">
            <span>Potencia</span>
            <b className={available ? undefined : 'nodata'}>{available ? `${num(percent, 1)} %` : 'Sin datos'}</b>
          </div>
        </div>
      </div>

      <div className="bar" style={{ '--accent': '#43a047' } as CSSProperties}>
        <i style={{ width: `${available && percent != null ? Math.max(0, Math.min(100, percent)) : 0}%` }} />
      </div>
    </div>
  );
}

/* ---------- Válvula ---------- */
export function ValveBlock({ open, available }: { open: number | null; available: boolean }) {
  const pct = available && open != null ? Math.max(0, Math.min(100, open)) : 0;
  const circumference = 251.3;
  return (
    <div className="dev-block">
      <div className="dev-head">
        <h3>Válvula proporcional</h3>
        <span className={`pill ${available ? 'pill-ok' : 'pill-idle'}`}>
          <i />
          {available ? 'Bajo supervisión' : 'Sin datos'}
        </span>
      </div>

      <div className="dev-figure">
        <div className="gauge-wrap">
          <svg width="132" height="132" viewBox="0 0 132 132" aria-hidden="true">
            <circle className="gauge-bg" cx="66" cy="66" r="40" />
            <circle
              className="gauge-val"
              cx="66"
              cy="66"
              r="40"
              transform="rotate(-90 66 66)"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - pct / 100)}
            />
            <text x="66" y="70" textAnchor="middle" fontSize="22" fontWeight="800" fill="#212121">
              {available ? num(pct, 1) : '—'}
            </text>
            <text x="66" y="88" textAnchor="middle" fontSize="10" fill="#757575">
              % apertura
            </text>
          </svg>
          <span className="gauge-unit">Señal de control desde el PLC</span>
        </div>

        <div className="dev-rows">
          <div className="dev-row">
            <span>Apertura</span>
            <b className={available && open != null ? undefined : 'nodata'}>{available && open != null ? `${num(open, 1)} %` : 'Sin datos'}</b>
          </div>
          <div className="dev-row">
            <span>Tipo de válvula</span>
            <b>Proporcional 4–20 mA</b>
          </div>
          <div className="dev-row">
            <span>Escritura</span>
            <b className="nodata">Bloqueada (solo lectura)</b>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Tablero de lámparas ---------- */
export interface LampSpec {
  id: string;
  label: string;
  color: 'green' | 'red' | 'blue' | 'yellow';
  on: boolean;
  sub?: string;
}

export function LampPanel({ lamps }: { lamps: LampSpec[] }) {
  return (
    <div className="lamp-panel">
      {lamps.map((lamp) => (
        <div key={lamp.id} className={`lamp${lamp.on ? ' on' : ''}`} data-color={lamp.color}>
          <span className="lamp-bulb" aria-hidden="true" />
          <div className="lamp-text">
            <b>{lamp.label}</b>
            <small>{lamp.sub ?? (lamp.on ? 'ACTIVADO' : 'DESACTIVADO')}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Controles deshabilitados ---------- */
export function ReadOnlyControls({ setpoint, mode }: { setpoint: number | null; mode: string }) {
  return (
    <div className="dev-block">
      <div className="dev-head">
        <h3>Comandos del módulo</h3>
        <span className="readonly-tag">
          <IconLock width="12" height="12" /> Solo lectura
        </span>
      </div>

      <div className="ro-controls">
        <div className="ro-field">
          <label htmlFor="ro-setpoint">Consigna de nivel</label>
          <div className="ro-value">
            <input id="ro-setpoint" value={setpoint != null ? `${num(setpoint, 2)} cm` : 'Sin datos'} readOnly disabled />
          </div>
        </div>
        <div className="ro-field">
          <label htmlFor="ro-mode">Modo de control</label>
          <select id="ro-mode" value={mode} disabled>
            <option>{mode}</option>
          </select>
        </div>
        <div className="ro-field">
          <label>Arranque / parada</label>
          <div className="ro-value" style={{ gap: 8 }}>
            <button type="button" className="btn" disabled>
              Arrancar
            </button>
            <button type="button" className="btn btn-ghost" disabled>
              Parar
            </button>
          </div>
        </div>
      </div>

      <p className="ro-note">
        <IconLock width="14" height="14" />
        Controles deshabilitados: la consigna, el arranque y la lógica de seguridad permanecen en el PLC
        192.168.114.9. Esta interfaz no escribe en ningún equipo de campo.
      </p>
    </div>
  );
}
