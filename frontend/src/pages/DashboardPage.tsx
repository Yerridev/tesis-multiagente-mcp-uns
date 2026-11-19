import { useMemo } from 'react';
import { usePlant } from '../context/PlantContext';
import type { Route } from '../router';
import { Banner, ErrorBlock, LoadingBlock } from '../components/common/States';
import { EquipmentCard } from '../components/equipment/EquipmentCard';
import { TrendChart } from '../components/charts/TrendChart';
import { IconAgent, IconArrow, IconDatabase, IconSignal } from '../components/common/Icons';
import { ageSeconds, formatAge, isStale, moduleMeta, num, timeOnly, valorMedible } from '../utils/format';

interface Props {
  onNavigate: (route: Route) => void;
}

/** SCADA de cada módulo (botón «Ver SCADA» de las tarjetas). */
const SCADA_DE: Record<string, Route> = { 'caudal-mcc09': 'mod-caudal', 'nivel-mcn09': 'nivel', 'presion-mcp09': 'mod-presion', 'temp-mct09': 'mod-temp' };

export function DashboardPage({ onNavigate }: Props) {
  const { equipment, historyFor, link, load, error, health, now, lastUpdate, reload } = usePlant();

  const charts = useMemo(
    () =>
      equipment.map((item) => ({
        id: item.id,
        label: `${moduleMeta(item.id).short} (${item.unit})`,
        color: moduleMeta(item.id).color,
        fill: true,
        points: historyFor(item.id)
          .slice(-240)
          .map((s) => ({ t: Date.parse(s.ts), v: s.value })),
      })),
    [equipment, historyFor],
  );

  if (load === 'loading') return <LoadingBlock />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  const online = equipment.filter((e) => e.status === 'ONLINE').length;
  const alarms = equipment.filter((e) => e.alarm).length;
  const stale = isStale(now, lastUpdate, 15);
  /* Sin datos reales (última marca en 1970 o > 24 h) no se reporta una antigüedad absurda */
  const edadTelemetria = ageSeconds(now, lastUpdate);
  const sinTelemetria = edadTelemetria == null || edadTelemetria > 86400;

  return (
    <>
      {link === 'disconnected' ? (
        <Banner tone="err">
          <b>Sin conexión con el canal SSE /api/stream.</b>
          <span className="spacer" />
          Los valores mostrados son los últimos recibidos; se reintentará automáticamente.
        </Banner>
      ) : null}

      {link !== 'disconnected' && stale && lastUpdate ? (
        <Banner tone="warn">
          <b>{sinTelemetria ? 'Sin telemetría real:' : 'Datos desactualizados:'}</b>{' '}
          {sinTelemetria
            ? 'ningún módulo está en línea; aquí aparecerán los datos en cuanto el equipo vuelva a reportar.'
            : `la última telemetría tiene ${formatAge(ageSeconds(now, lastUpdate))}.`}
        </Banner>
      ) : null}

      {equipment.some((e) => !valorMedible(e.calidad)) ? (
        <Banner tone="warn">
          <b>Medida no válida:</b>{' '}
          {equipment
            .filter((e) => !valorMedible(e.calidad))
            .map((e) => `${e.name} (sensor fuera de rango)`)
            .join('; ')}
          . El valor publicado es el tope de saturación de la escala, no la medida real: verifica el
          sensor y el nivel físico antes de operar.
        </Banner>
      ) : null}

      <section className="dash-hero">
        <div>
          <div className="eyebrow">Centro de operaciones</div>
          <h2>Planta industrial · Laboratorio USS</h2>
          <p>Supervisión en tiempo real de caudal, nivel, presión y temperatura con agentes MCP de solo lectura.</p>
        </div>
        <div className="hero-meta">
          <span className="pill pill-dark">
            <i /> Modo supervisión
          </span>
          <span className={`pill ${link === 'connected' ? 'pill-ok pill-live' : 'pill-warn'}`}>
            <i /> SSE {link === 'connected' ? 'en vivo' : link}
          </span>
          <span className="pill pill-dark">
            <i /> Última telemetría {lastUpdate ? timeOnly(lastUpdate) : '—'}
          </span>
        </div>
      </section>

      <section className="status-bar" aria-label="Estado de la plataforma">
        <div className={`status-chip ${health === 'ok' ? 'ok' : health === 'error' ? 'err' : 'warn'}`}>
          <span className="dot" />
          <div>
            <strong>API REST</strong>
            <small>
              {health === 'ok' ? 'ASP.NET Core · /api/equipment' : health === 'error' ? 'Sin respuesta del backend' : 'Verificando…'}
            </small>
          </div>
        </div>
        <div className={`status-chip ${link === 'connected' ? 'ok' : link === 'disconnected' ? 'err' : 'warn'}`}>
          <span className="dot" />
          <div>
            <strong>SSE /api/stream</strong>
            <small>
              {link === 'connected'
                ? 'Telemetría cada 1 s'
                : link === 'reconnecting'
                  ? 'Reconectando…'
                  : link === 'connecting'
                    ? 'Estableciendo canal…'
                    : 'Canal caído'}
            </small>
          </div>
        </div>
        <div className={`status-chip ${online === equipment.length ? 'ok' : online > 0 ? 'warn' : 'err'}`}>
          <span className="dot" />
          <div>
            <strong>Equipos en línea</strong>
            <small>
              {online} de {equipment.length} respondiendo
            </small>
          </div>
        </div>
        <div className={`status-chip ${alarms === 0 ? 'ok' : 'err'}`}>
          <span className="dot" />
          <div>
            <strong>Alarmas de proceso</strong>
            <small>{alarms === 0 ? 'Sin alarmas activas' : `${alarms} equipo(s) fuera de banda`}</small>
          </div>
        </div>
      </section>

      <div className="section-title">
        <div>
          <div className="eyebrow">Planta</div>
          <h2>Módulos de control</h2>
          <p>Controlador, dirección IP, valor, consigna y antigüedad del dato de cada equipo.</p>
        </div>
        <span className="readonly-tag">MODO SUPERVISIÓN · SOLO LECTURA</span>
      </div>

      <section className="eq-grid">
        {equipment.map((item) => (
          <EquipmentCard
            key={item.id}
            equipment={item}
            now={now}
            points={historyFor(item.id).slice(-40).map((s) => ({ t: Date.parse(s.ts), v: s.value }))}
            action={
              /* Ver SCADA en los 4 módulos (antes solo nivel) */
              SCADA_DE[item.id] ? (
                <button type="button" className="eq-link" onClick={() => onNavigate(SCADA_DE[item.id])}>
                  Ver SCADA <IconArrow width="14" height="14" />
                </button>
              ) : null
            }
          />
        ))}
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Telemetría en tiempo real</h2>
            <span className="panel-sub">
              Serie en vivo recibida por SSE · {historyFor(equipment[0]?.id ?? '').length} muestras en búfer
            </span>
          </div>
          <span className={`pill ${link === 'connected' ? 'pill-ok pill-live' : 'pill-idle'}`}>
            <i />
            {link === 'connected' ? 'Recibiendo' : 'En pausa'}
          </span>
        </div>
        <TrendChart series={charts} size="tall" emptyText="Esperando la primera telemetría del canal SSE…" />
      </section>

      {/* Antes era la página "Monitoreo en tiempo real" */}
      <section className="cards-live">
        {equipment.map((item) => (
          <div className={`live-box live-${item.id.split('-')[0]}`} key={item.id}>
            <span>{moduleMeta(item.id).short}</span>
            <b className={valorMedible(item.calidad) ? undefined : 'nodata'}>
              {valorMedible(item.calidad) ? num(item.value, 2) : 'n/d'}
            </b>
            <small>
              {item.unit} · consigna {num(item.setpoint, 1)} {item.unit} · {moduleMeta(item.id).label}
              {valorMedible(item.calidad) ? '' : ' · SIN MEDIDA (sensor fuera de rango)'}
            </small>
          </div>
        ))}
      </section>

      <section className="panel teaser">
        <div className="teaser-ico">
          <IconAgent width="26" height="26" />
        </div>
        <div className="teaser-body">
          <h3>Agente MCP de supervisión</h3>
          <p>
            Consulta el estado de la planta, las alarmas y el historial con herramientas de solo lectura sobre
            /api/equipment y /api/history, con asistente por IA (OpenRouter) cuando está disponible. Escritura al PLC
            deshabilitada.
          </p>
        </div>
        <button type="button" className="btn" onClick={() => onNavigate('agents')}>
          Abrir panel <IconArrow width="15" height="15" />
        </button>
      </section>

      <p className="panel-sub" style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <IconSignal width="14" height="14" /> Canal SSE /api/stream
        </span>
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <IconDatabase width="14" height="14" /> API /api/equipment · /api/history
        </span>
            <span>Sensores: Kobold (caudal) · SENIX TS-30S1 (nivel) · transductor de presión · INDUCONTROL MCT-09 (temperatura)</span>
      </p>
    </>
  );
}
