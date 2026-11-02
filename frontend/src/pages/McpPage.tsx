import { useEffect, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { api } from '../services/api';
import type { AgentTool } from '../types';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { IconDatabase, IconHistory, IconSignal } from '../components/common/Icons';

const SERVERS = [
  {
    key: 'tiempo-real',
    name: 'Origen de datos en tiempo real',
    desc: 'Refleja el estado de /api/equipment y la señal del hub SignalR.',
  },
  {
    key: 'histórico',
    name: 'Origen de datos histórico',
    desc: 'Consulta el búfer /api/history (historial en memoria del backend).',
  },
  {
    key: 'análisis',
    name: 'Origen de análisis',
    desc: 'Agente IA (OpenRouter) con herramientas de solo lectura sobre los equipos.',
  },
];

const SERVER_ICON: Record<string, typeof IconSignal> = {
  'tiempo-real': IconSignal,
  'histórico': IconHistory,
  'análisis': IconDatabase,
};

export function McpPage() {
  const { link, health, history, load, error, reload } = usePlant();
  const [tools, setTools] = useState<AgentTool[] | null>(null);

  useEffect(() => {
    api
      .agentTools()
      .then(setTools)
      .catch(() => setTools([]));
  }, []);

  if (load === 'loading') return <LoadingBlock />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  return (
    <>
      <section className="srv-grid">
        {SERVERS.map((server) => {
          const Icon = SERVER_ICON[server.key] ?? IconDatabase;
          const serverTools = (tools ?? []).filter((t) => t.server === server.key);
          const state =
            server.key === 'tiempo-real'
              ? link === 'connected'
                ? 'ok'
                : link === 'disconnected'
                  ? 'err'
                  : 'busy'
              : server.key === 'histórico'
                ? history.length
                  ? 'ok'
                  : 'pending'
                : health === 'ok'
                  ? 'ok'
                  : health === 'error'
                    ? 'err'
                    : 'pending';
          return (
            <article className="srv-card" key={server.key}>
              <div className="srv-head">
                <span className={`srv-dot ${state}`} />
                <span className="srv-name">{server.name}</span>
              </div>
              <p className="srv-desc">{server.desc}</p>
              <span className="srv-tools-label">Herramientas disponibles · {serverTools.length}</span>
              <ul className="srv-tools">
                {serverTools.length === 0 ? (
                  <li className="muted">sin herramientas publicadas</li>
                ) : (
                  serverTools.map((tool) => (
                    <li key={tool.name} title={tool.description}>
                      {tool.name}
                    </li>
                  ))
                )}
              </ul>
              <p className="srv-desc" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <Icon width="14" height="14" /> Estado derivado de la señal real correspondiente
              </p>
            </article>
          );
        })}
      </section>

      <p className="agent-note">
        <b>Origen de la información:</b> <code>/api/agent/tools</code> publica las herramientas del agente. Los datos
        provienen de <code>/api/equipment</code>, <code>/api/history</code> y <code>/hubs/plant</code>; todas las
        herramientas son de solo lectura y ninguna escribe en el PLC.
      </p>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Registro de llamadas</h2>
            <span className="panel-sub">Trazabilidad de llamadas · resultado y duración</span>
          </div>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Hora</th>
                <th>Agente</th>
                <th>Herramienta</th>
                <th>Resultado</th>
                <th>Tiempo</th>
              </tr>
            </thead>
            <tbody>
              <tr className="table-empty">
                <td colSpan={5} className="empty">
                  Sin llamadas registradas en esta vista: el registro se poblará en «Agentes de IA» cuando envíes una
                  consulta al asistente.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
