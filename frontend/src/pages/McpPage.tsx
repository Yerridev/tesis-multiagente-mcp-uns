import { useEffect, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { api } from '../services/api';
import type { AgentTool } from '../types';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { McpFlow } from '../components/agents/McpFlow';

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

  const estadoDe = (key: string) =>
    key === 'tiempo-real'
      ? link === 'connected' ? 'ok' : link === 'disconnected' ? 'err' : 'busy'
      : key === 'histórico'
        ? history.length ? 'ok' : 'pending'
        : health === 'ok' ? 'ok' : health === 'error' ? 'err' : 'pending';

  return (
    <>
      <div className="mcp-grid">
        <section className="panel mcp-srv">
          <div className="panel-head">
            <div>
              <h2>Servidores MCP</h2>
              <span className="panel-sub">Cada servidor con sus herramientas · {(tools ?? []).length} herramienta(s) publicadas</span>
            </div>
          </div>
          {tools === null ? (
            <div className="af-wrap mf-wrap" style={{ display: 'grid', placeItems: 'center', color: 'var(--muted)' }}>Cargando herramientas…</div>
          ) : (
            <McpFlow servidores={SERVERS.map((s) => ({ ...s, estado: estadoDe(s.key) }))} tools={tools} />
          )}
        </section>

      <section className="panel mcp-reg">
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
      </div>

      <p className="agent-note">
        <b>Origen de la información:</b> <code>/api/agent/tools</code> publica las herramientas del agente. Los datos
        provienen de <code>/api/equipment</code>, <code>/api/history</code> y <code>/hubs/plant</code>; todas las
        herramientas son de solo lectura y ninguna escribe en el PLC.
      </p>
    </>
  );
}
