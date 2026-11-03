import type { CSSProperties, ReactNode } from 'react';
import type { Equipment, SeriesPoint } from '../../types';
import { ageSeconds, clamp, formatAge, isStale, moduleMeta, num, timeOnly, valorMedible } from '../../utils/format';
import { Sparkline } from '../charts/Sparkline';
import { IconFlow, IconGauge, IconTank, IconThermometer } from '../common/Icons';

const ICONS: Record<string, typeof IconFlow> = {
  'caudal-mcc09': IconFlow,
  'nivel-mcn09': IconTank,
  'presion-mcp09': IconGauge,
  'temp-mct09': IconThermometer,
};

interface Props {
  equipment: Equipment;
  now: number;
  points: SeriesPoint[];
  action?: ReactNode;
}

export function EquipmentCard({ equipment, now, points, action }: Props) {
  const meta = moduleMeta(equipment.id);
  const Icon = ICONS[equipment.id] ?? IconFlow;
  const age = ageSeconds(now, equipment.timestamp);
  const stale = isStale(now, equipment.timestamp);
  const offline = equipment.status !== 'ONLINE';
  const alarm = equipment.alarm && !offline;
  const sinConsigna = !(equipment.setpoint > 0);
  /* Sensor saturado: el valor publicado es el tope de la escala, no una medida */
  const medible = valorMedible(equipment.calidad);
  /* Sin comunicación (o sin medida válida) no se presentan valores: «Sin datos» en lugar de un número viejo */
  const hasData = !offline && medible && Number.isFinite(equipment.value);
  const sinDatoAlarma = sinConsigna || offline || !medible;

  const scaleMax = Math.max(equipment.setpoint * 1.5, equipment.value ?? 0, 1);
  const width = clamp(((equipment.value ?? 0) / scaleMax) * 100);
  const marker = clamp((equipment.setpoint / scaleMax) * 100);

  return (
    <article
      className={`eq-card${alarm ? ' is-alarm' : ''}${offline ? ' is-offline' : ''}`}
      style={{ '--accent': meta.color } as CSSProperties}
    >
      <div className="eq-top">
        <div className="eq-icon">
          <Icon />
        </div>
        <div className="eq-title">
          <h3>{meta.short}</h3>
          <small>{equipment.id}</small>
        </div>
        <span className={`pill ${offline ? 'pill-err' : medible ? 'pill-ok' : 'pill-warn'}`}>
          <i />
          {offline ? equipment.status : medible ? equipment.status : 'SIN MEDIDA'}
        </span>
      </div>

      <div>
        <div className="eq-var">{equipment.variable}</div>
        <div className="eq-value">
          <b className={hasData ? undefined : 'nodata'}>{hasData ? num(equipment.value, 1) : 'Sin datos'}</b>
          {hasData ? <span>{equipment.unit}</span> : null}
        </div>
      </div>

      <div>
        <div className="bar">
          <i style={{ width: hasData ? `${width.toFixed(1)}%` : '0%' }} />
          <span className="bar-sp" style={{ left: `${marker.toFixed(1)}%` }} title="Consigna" />
        </div>
        <div className="eq-meta">
          <span>
            Consigna{' '}
            <b className="num">{sinConsigna ? 'Sin datos' : num(equipment.setpoint, 1)}</b>{' '}
            {sinConsigna ? '' : equipment.unit}
          </span>
          <span className={`age${stale ? ' stale' : ''}`}>{stale ? 'Sin datos' : formatAge(age)}</span>
        </div>
      </div>

      <div className="eq-rows">
        <div className="eq-row">
          <span>Controlador</span>
          <b>{equipment.controller}</b>
        </div>
        <div className="eq-row">
          <span>Dirección IP</span>
          <code>{equipment.ip}</code>
        </div>
        <div className="eq-row">
          <span>Desviación</span>
          <b>
            {sinConsigna || !hasData ? 'Sin datos' : `${num(equipment.deviation, 2)} ${equipment.unit}`}
          </b>
        </div>
        <div className="eq-row">
          <span>Último dato</span>
          <b>{offline ? 'Sin datos' : timeOnly(equipment.timestamp)}</b>
        </div>
      </div>

      <Sparkline points={points} color={meta.color} />

      <div className="eq-foot">
        <span className={`pill ${sinDatoAlarma ? 'pill-idle' : alarm ? 'pill-err' : 'pill-ok'}`}>
          <i />
          {sinDatoAlarma ? 'Sin datos de alarma' : alarm ? 'Alarma activa' : 'Sin alarma'}
        </span>
        {action}
      </div>
    </article>
  );
}
