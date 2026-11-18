import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { AgentTool, CatalogoMcpRespuesta } from '../types';
import { McpFlow, type ServidorMcp } from '../components/agents/McpFlow';

/* Los 4 servidores MCP del sistema multiagente (uno por módulo). Si el bat 31 no corre, se muestran en gris. */
const BASE: { modulo: string; nombre: string; desc: string; puerto: number }[] = [
  { modulo: 'nivel', nombre: 'Nivel', desc: 'MCN-09 · MicroLogix 1100 · :8001', puerto: 8001 },
  { modulo: 'caudal', nombre: 'Caudal', desc: 'MCC-09 · S7-200 · :8002', puerto: 8002 },
  /* orden de la cuadrícula: arriba Nivel | Caudal · abajo Temperatura | Presión */
  { modulo: 'temperatura', nombre: 'Temperatura', desc: 'MCT-09 · Twido · :8004', puerto: 8004 },
  { modulo: 'presion', nombre: 'Presión', desc: 'MCP-09 · cFP-2200 · :8003', puerto: 8003 },
];

export function McpPage() {
  const [datos, setDatos] = useState<CatalogoMcpRespuesta | null>(null);

  useEffect(() => {
    let vivo = true;
    const cargar = () => api.mcpCatalogo().then((d) => vivo && setDatos(d)).catch(() => vivo && setDatos({ disponible: false, catalogo: null }));
    void cargar();
    const id = window.setInterval(cargar, 15000);   // el orquestador refresca el catálogo cada 15 s
    return () => { vivo = false; window.clearInterval(id); };
  }, []);

  const disponible = datos?.disponible === true;
  const cat = datos?.catalogo?.servidores ?? [];
  const servidores: ServidorMcp[] = BASE.map((b) => {
    const s = cat.find((x) => x.modulo === b.modulo);
    const ok = disponible && s?.en_linea;
    return { key: b.modulo, name: b.nombre, desc: ok ? `${b.desc} · respondió en ${s?.ms ?? '?'} ms` : `${b.desc} · fuera de línea`, estado: datos === null ? 'busy' : ok ? 'ok' : 'err' };
  });
  const tools: AgentTool[] = disponible
    ? cat.flatMap((s) => s.herramientas.map((h) => ({ name: h.nombre, server: s.modulo, description: h.descripcion })))
    : [];
  const llamadas = disponible ? datos?.catalogo?.llamadas ?? [] : [];
  const total = tools.length;

  return (
    <>
      <div className="mcp-grid">
        <section className="panel mcp-srv">
          <div className="panel-head">
            <div>
              <h2>Servidores MCP</h2>
              <span className="panel-sub">
                {datos === null ? 'Consultando…'
                  : disponible ? `${servidores.filter((s) => s.estado === 'ok').length} de 4 en línea · ${total} herramientas publicadas (list_tools real)`
                  : 'Sistema multiagente fuera de línea · abre el bat 31'}
              </span>
            </div>
          </div>
          <McpFlow servidores={servidores} tools={tools} />
        </section>

        <section className="panel mcp-reg">
          <div className="panel-head">
            <div>
              <h2>Registro de llamadas</h2>
              <span className="panel-sub">Últimas llamadas de los agentes a sus servidores MCP · resultado y duración</span>
            </div>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Hora</th>
                  <th>Agente</th>
                  <th>Servidor · herramienta</th>
                  <th>Resultado</th>
                  <th>Tiempo</th>
                </tr>
              </thead>
              <tbody>
                {llamadas.length === 0 ? (
                  <tr className="table-empty">
                    <td colSpan={5} className="empty">
                      {disponible
                        ? 'Sin llamadas aún: pregunta algo en «Agentes de IA» y aquí aparecerá cada herramienta usada.'
                        : 'El sistema multiagente no está corriendo (bat 31).'}
                    </td>
                  </tr>
                ) : (
                  llamadas.map((l, i) => (
                    <tr key={`${l.corr}-${i}`}>
                      <td>{l.ts ? new Date(l.ts).toLocaleTimeString('es-PE', { hour12: false }) : '—'}</td>
                      <td style={{ fontWeight: 700 }}>{l.agente}</td>
                      <td>{l.servidor} · {l.herramienta}</td>
                      <td><span className={`tag ${l.ok ? 'tag-ok' : 'tag-err'}`}>{l.ok ? 'OK' : 'ERROR'}</span></td>
                      <td>{l.ms} ms</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <p className="agent-note">
        <b>Origen de la información:</b> cada 15 s el orquestador le pregunta a los 4 servidores MCP qué herramientas
        publican (<code>list_tools</code>) y lo deja en MQTT; esta página lo lee de <code>/api/mcp/catalogo</code>.
        Todas las herramientas son de solo lectura: ninguna escribe en el PLC.
      </p>
    </>
  );
}
