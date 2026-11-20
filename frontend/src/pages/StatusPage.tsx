import type { ReactNode } from 'react';
import { usePlant } from '../context/PlantContext';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { ageSeconds, formatAge, isStale } from '../utils/format';
import { IconClock, IconDatabase, IconPlc, IconServer, IconSignal } from '../components/common/Icons';

export function StatusPage() {
  const { equipment, link, health, load, error, reload, now, lastUpdate } = usePlant();

  if (load === 'loading') return <LoadingBlock />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  const stale = isStale(now, lastUpdate, 15);
  const rows: Array<{ ico: ReactNode; name: string; sub: string; cls: string; label: string }> = [
    {
      ico: <IconServer />,
      name: 'API REST · Python FastAPI',
      sub: 'GET /api/health · /api/equipment · /api/history',
      cls: health === 'ok' ? 'sys-ok' : health === 'error' ? 'sys-err' : 'sys-warn',
      label: health === 'ok' ? 'Operativo' : health === 'error' ? 'Inaccesible' : 'Verificando…',
    },
    {
      ico: <IconSignal />,
      name: 'Canal SSE · /api/stream',
      sub: 'Telemetría en tiempo real cada 1 s',
      cls: link === 'connected' ? 'sys-ok' : link === 'disconnected' ? 'sys-err' : 'sys-warn',
      label:
        link === 'connected' ? 'Conectado' : link === 'reconnecting' ? 'Reconectando' : link === 'connecting' ? 'Conectando' : 'Desconectado',
    },
    ...equipment.map((item) => ({
      ico: <IconPlc />,
      name: `PLC ${item.controller}`,
      sub: `${item.ip} · ${item.variable} · solo lectura`,
      cls: item.status === 'ONLINE' ? 'sys-ok' : 'sys-err',
      label: item.status === 'ONLINE' ? 'Operativo' : 'Sin comunicación',
    })),
    {
      ico: <IconDatabase />,
      name: 'Fuente de datos',
      sub: 'API REST + SSE · historial en memoria del backend (30 min por equipo)',
      cls: 'sys-warn',
      label: 'En memoria',
    },
    {
      ico: <IconClock />,
      name: 'Última telemetría',
      sub: lastUpdate ? `${formatAge(ageSeconds(now, lastUpdate))} · ${new Date(lastUpdate).toLocaleTimeString('es-PE', { hour12: false })}` : 'Sin datos',
      cls: stale ? 'sys-warn' : 'sys-ok',
      label: stale ? 'Desactualizada' : 'Fresca',
    },
  ];

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Estado del sistema</h2>
        <span className="panel-sub">Verificación en vivo · sin inventar estados</span>
      </div>
      <div className="sys-list">
        {rows.map((row) => (
          <div className="sys-row" key={row.name}>
            <div className="sys-left">
              <div className="sys-ico" aria-hidden="true">
                {row.ico}
              </div>
              <div>
                <strong>{row.name}</strong>
                <small>{row.sub}</small>
              </div>
            </div>
            <span className={`sys-badge ${row.cls}`}>{row.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
