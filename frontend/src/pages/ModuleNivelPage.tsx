import { useEffect, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { api } from '../services/api';
import type { LevelDetail } from '../types';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { LampPanel, type LampSpec } from '../components/scada/Devices';
import { IconBarChart, IconPanel } from '../components/common/Icons';
import { ageSeconds, clamp, formatAge, isStale, levelAlarms, num, timeOnly, valorMedible } from '../utils/format';

const ID = 'nivel-mcn09';

export function ModuleNivelPage() {
  const { byId, load, error, reload, now, link } = usePlant();
  const [detail, setDetail] = useState<LevelDetail | null>(null);
  const eq = byId[ID];

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      api
        .levelDetail()
        .then((data) => {
          if (!cancelled) {
            setDetail(data);
          }
        })
        .catch(() => {
          /* se conserva el último detalle válido */
        });
    };
    tick();
    const id = window.setInterval(tick, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (load === 'loading') return <LoadingBlock />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;
  if (!eq) {
    return <ErrorBlock title="Equipo nivel-mcn09 no disponible" message="La API /api/equipment no lo devolvió." onRetry={reload} />;
  }

  const age = ageSeconds(now, eq.timestamp);
  const stale = isStale(now, eq.timestamp, 15);
  /* Sensor saturado: el valor en cm es el tope de la escala, no una medida */
  const medible = valorMedible(eq.calidad) && valorMedible(detail?.calidad);
  const { high, low } = levelAlarms(eq.value, eq.setpoint);
  /* Sin consigna real no se evalúa la alarma; sin comunicación no se presentan valores */
  const sinConsigna = !(eq.setpoint > 0);
  const sinDato = eq.status !== 'ONLINE' || !medible;
  const percent = detail?.percent != null ? clamp(detail.percent) : null;
  const fillClass = percent !== null && percent >= 90 ? 'crit' : percent !== null && percent >= 70 ? 'warn' : '';
  const knobDeg = (detail?.vfdPercent ?? 0) * 2.7 - 135;

  const lamps: LampSpec[] = [
    { id: 'modo', label: 'Modo', color: 'blue', on: Boolean(detail), sub: detail ? detail.mode : 'Sin datos' },
    { id: 'energizado', label: 'Energizado', color: 'yellow', on: false, sub: 'Sin datos' },
    { id: 'funcionando', label: 'Sistema funcionando', color: 'green', on: Boolean(detail?.pumpOn) },
    { id: 'arranque', label: 'Arranque manual', color: 'green', on: false, sub: 'Sin datos' },
    { id: 'parada', label: 'Parada manual', color: 'red', on: false, sub: 'Sin datos' },
    { id: 'alto', label: 'Alarma nivel alto', color: 'red', on: high, sub: sinConsigna ? 'Sin datos' : undefined },
    { id: 'bajo', label: 'Alarma nivel bajo', color: 'red', on: low, sub: sinConsigna ? 'Sin datos' : undefined },
  ];

  return (
    <div className="nv-wrap">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>
              <span className="ico-inline">
                <IconPanel />
              </span>
              Tablero del módulo de nivel
            </h2>
            <span className="panel-sub">
              {detail?.controller ?? eq.controller} · {detail?.plcIp ?? eq.ip} · solo lectura
            </span>
          </div>
          <span className={`pill ${eq.status === 'ONLINE' ? 'pill-ok' : 'pill-err'}`}>
            <i />
            {eq.status}
          </span>
        </div>

        <LampPanel lamps={lamps} />

        <div className="lamp" data-color="blue" style={{ marginTop: 9 }}>
          <span className="pl-knob" aria-hidden="true">
            <i style={{ transform: `rotate(${knobDeg}deg)` }} />
          </span>
          <div className="lamp-text">
            <b>Potencia de motor</b>
            <small>
              {detail?.vfdPercent != null && detail.vfdHz != null
                ? `${num(detail.vfdPercent, 1)} % · ${num(detail.vfdHz, 1)} Hz`
                : 'Sin datos'}
            </small>
          </div>
        </div>

        <p className="ro-note" style={{ marginTop: 12 }}>
          Indicadores en vivo desde la telemetría. No hay controles: este módulo no escribe al PLC. Las señales sin
          fuente disponible se muestran como «Sin datos».
        </p>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>
              <span className="ico-inline">
                <IconBarChart />
              </span>
              Nivel del tanque
            </h2>
            <span className="panel-sub">
              SENIX TS-30S1 ·{' '}
              {detail?.tankHeight != null ? `${num(detail.tankHeight, 0)} ${eq.unit} de altura` : 'altura sin datos'}
            </span>
          </div>
          <span className={`pill ${high || low ? 'pill-err' : stale ? 'pill-warn' : 'pill-ok pill-live'}`}>
            <i />
              {sinConsigna
                ? 'Sin datos'
                : high
                  ? 'Alarma alta'
                  : low
                    ? 'Alarma baja'
                    : stale
                      ? 'Sin comunicación'
                      : 'En vivo'}
          </span>
        </div>

          <div className="nv-gauge">
            <div className="nv-gaugeBar">
              <i className={fillClass ?? ''} style={{ width: `${(percent ?? 0).toFixed(1)}%` }} />
            </div>
            <div className="nv-gaugeVal">
              <b>{sinDato ? 'Sin datos' : num(eq.value, 2)}</b>
              {sinDato ? null : <span>{eq.unit}</span>}
            </div>
          </div>

          <div className="dev-rows">
            <div className="dev-row">
              <span>Nivel (%)</span>
              <b>{percent != null ? `${num(percent, 1)} %` : 'Sin datos'}</b>
            </div>
            <div className="dev-row">
              <span>Setpoint</span>
              <b>{sinConsigna ? 'Sin datos' : `${num(eq.setpoint, 2)} ${eq.unit}`}</b>
            </div>
          <div className="dev-row">
            <span>Última lectura</span>
            <b>{timeOnly(eq.timestamp)}</b>
          </div>
          <div className="dev-row">
            <span>Origen</span>
            <b>API + SignalR (simulación)</b>
          </div>
          <div className="dev-row">
            <span>Comunicación</span>
            <b className={eq.status === 'ONLINE' ? undefined : 'nodata'}>
              {eq.status === 'ONLINE' ? 'PLC EN LÍNEA' : 'PLC SIN COMUNICACIÓN'}
            </b>
          </div>
          <div className="dev-row">
            <span>Antigüedad</span>
            <b className={stale ? 'nodata' : undefined}>{formatAge(age)}</b>
          </div>
        </div>

        <p className="ro-note" style={{ marginTop: 12 }}>
          {stale
            ? `Sin comunicación: la última lectura fue hace ${age ?? 0} s (canal ${link}).`
            : 'Lectura en vivo recibida por SignalR cada 1 s. Sin escrituras al PLC.'}
        </p>
      </section>
    </div>
  );
}
