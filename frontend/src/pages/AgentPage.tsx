import { useEffect, useMemo, useRef, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { api } from '../services/api';
import type { AgentCall, AgentStatus } from '../types';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { IconArrow } from '../components/common/Icons';

interface ChatMessage {
  id: number;
  role: 'user' | 'agent';
  text: string;
  tools?: AgentCall[];
  model?: string | null;
}

interface Action {
  ts: string;
  agent: string;
  what: string;
  ok: boolean;
}

const AGENTES = [
  { key: 'orquestador', name: 'Agente Orquestador', desc: 'Recibe tu pregunta y reparte el trabajo a los demás', server: 'Ninguno directo (delega)' },
  { key: 'ingesta', name: 'Agente de Ingesta', desc: 'Trae los datos que llegan del PLC', server: 'Tiempo real' },
  { key: 'validacion', name: 'Agente de Validación y Calidad', desc: 'Revisa si un dato es válido o está fuera de rango', server: 'Tiempo real' },
  { key: 'analisis', name: 'Agente de Análisis', desc: 'Busca anomalías y tendencias', server: 'Histórico y análisis' },
  { key: 'reportes', name: 'Agente de Reportes y Trazabilidad', desc: 'Arma informes y guarda qué se hizo', server: 'Histórico y análisis y trazabilidad' },
];

const TOOL_AGENT: Record<string, string> = {
  estado_planta: 'Agente de Ingesta',
  leer_equipo: 'Agente de Ingesta',
  estado_plc: 'Agente de Ingesta',
  verificar_alarma: 'Agente de Validación y Calidad',
  resumen_historico: 'Agente de Análisis',
  ayuda: 'Agente Orquestador',
};

const AGENT_KEY = (key: string) => `mcp-agente-${key}`;

export function AgentPage() {
  const { link, health, history, load, error, reload } = usePlant();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  useEffect(() => {
    api
      .agentStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    const initial: Record<string, boolean> = {};
    for (const agent of AGENTES) {
      try {
        initial[agent.key] = localStorage.getItem(AGENT_KEY(agent.key)) === 'open';
      } catch {
        initial[agent.key] = false;
      }
    }
    setOpen(initial);
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages, busy]);

  const dotState = (key: string): string => {
    switch (key) {
      case 'orquestador':
        return busy ? 'busy' : health === 'ok' ? 'ok' : health === 'error' ? 'err' : 'pending';
      case 'ingesta':
        return link === 'connected' ? 'ok' : link === 'disconnected' ? 'err' : 'busy';
      case 'validacion':
        return link === 'connected' ? 'ok' : 'pending';
      case 'analisis':
        return history.length ? 'ok' : 'pending';
      case 'reportes':
        return actions.length ? 'ok' : 'pending';
      default:
        return 'pending';
    }
  };

  const lastTask = (agentName: string) => {
    const found = actions.find((a) => a.agent === agentName);
    if (!found) return agentName === 'Agente Orquestador' ? 'Sin tareas aún' : 'Sin tareas registradas';
    return found.what;
  };

  const llm = status?.mode === 'llm';
  const modeText = llm
    ? `IA activa · OpenRouter · ${status?.model} · límite 50 consultas/día`
    : 'Motor de reglas · sin modelo LLM conectado';

  const toggleCard = (key: string) => {
    setOpen((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(AGENT_KEY(key), next[key] ? 'open' : 'closed');
      } catch {
        /* almacenamiento no disponible */
      }
      return next;
    });
  };

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || busy) return;
    setInput('');
    setFailure(null);
    setMessages((prev) => [...prev, { id: nextId.current++, role: 'user', text: message }]);
    setBusy(true);
    try {
      const reply = await api.agentAsk(message);
      setMessages((prev) => [...prev, { id: nextId.current++, role: 'agent', text: reply.reply, tools: reply.tools, model: reply.model ?? null }]);
      setActions((prev) => {
        const rows: Action[] = reply.tools.map((tool) => ({
          ts: reply.ts,
          agent: TOOL_AGENT[tool.name] ?? 'Agente Orquestador',
          what: `${tool.name}: ${tool.result}`,
          ok: tool.ok,
        }));
        rows.push({
          ts: reply.ts,
          agent: 'Agente Orquestador',
          what: `Respondió a: «${message}»${reply.tools.length ? ` · usó ${reply.tools.map((t) => t.name).join(', ')}` : ''}`,
          ok: true,
        });
        return [...rows.reverse(), ...prev].slice(0, 50);
      });
    } catch (err) {
      const detail = err instanceof Error ? err.message : 'Error desconocido';
      setFailure(detail);
      setMessages((prev) => [
        ...prev,
        {
          id: nextId.current++,
          role: 'agent',
          text: 'No se pudo contactar con el asistente. Verifica que el backend ASP.NET Core esté ejecutándose.',
        },
      ]);
      setActions((prev) =>
        [
          { ts: new Date().toISOString(), agent: 'Agente Orquestador', what: `Intentó responder: «${message}»`, ok: false },
          ...prev,
        ].slice(0, 50),
      );
    } finally {
      setBusy(false);
    }
  };

  const agentCards = useMemo(() => AGENTES, []);

  if (load === 'loading') return <LoadingBlock label="Preparando los agentes de IA…" />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  return (
    <div className="agents-view">
      {/* 5 agentes de la arquitectura (tarjetas contraíbles) */}
      <div className="cards cards-agents">
        {agentCards.map((agent) => (
          <div className={`agent-card${open[agent.key] ? ' open' : ''}`} data-agent={agent.key} key={agent.key}>
            <button
              type="button"
              className="agent-toggle"
              aria-expanded={open[agent.key] ? 'true' : 'false'}
              onClick={() => toggleCard(agent.key)}
            >
              <span className={`srv-dot ${dotState(agent.key)}`} />
              <span className="agent-name">{agent.name}</span>
              <span className="agent-caret">▸</span>
            </button>
            <div className="agent-body">
              <div className="agent-body-inner">
                <div className="agent-pad">
                  <p className="agent-desc">{agent.desc}</p>
                  <div className="agent-row">
                    <span className="agent-k">Usa el servidor MCP de</span>
                    <span className="agent-v">{agent.server}</span>
                  </div>
                  <div className="agent-row">
                    <span className="agent-k">Última tarea</span>
                    <span className={`agent-v agent-task${lastTask(agent.name).startsWith('Sin') ? ' is-empty' : ''}`}>
                      {lastTask(agent.name)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="agents-note">
        {llm ? (
          <>
            <b>IA ACTIVA · OPENROUTER:</b> el asistente consulta el modelo <code>{status?.model}</code> con los datos en
            vivo de <code>/api/equipment</code>, <code>/api/history</code> y <code>/hubs/plant</code> (50 consultas
            gratis al día). Las herramientas son deterministas y de solo lectura: <b>sin escritura al PLC</b>. Toca una
            tarjeta para ver sus detalles.
          </>
        ) : (
          <>
            <b>MOTOR DE REGLAS:</b> punto de estado = señal real del equipo (verde activo · naranja ocupado · rojo caído
            · gris sin verificar). Las respuestas se resuelven con reglas deterministas sobre los datos en vivo; el
            modelo LLM se activa al configurar <code>OPENROUTER_API_KEY</code>. Toca una tarjeta para ver sus detalles.
          </>
        )}
      </p>

      <div className="agents-bottom">
        {/* Chat (atendido por el Agente Orquestador) */}
        <section className="panel panel-chat">
          <div className="panel-head">
            <div>
              <h2>Asistente de agentes IA</h2>
              <span className="panel-sub" id="chatStatus">
                {busy ? (llm ? 'Consultando la IA…' : 'Consultando el asistente…') : modeText}
              </span>
            </div>
            {llm ? (
              <span className="pill pill-ok pill-live">
                <i />
                IA ACTIVA
              </span>
            ) : (
              <span className="readonly-tag">MOTOR DE REGLAS</span>
            )}
          </div>

          <div className="chat-log" ref={logRef}>
            {messages.length === 0 ? (
              <div className="msg msg-agent">
                <div className="msg-body">
                  {llm
                    ? 'Hola. Soy el asistente de MCP-INDUSTRIAL (IA vía OpenRouter, me atiende el Agente Orquestador). Pregúntame por caudal, nivel, presión o temperatura: respondo con los datos en vivo de la planta.'
                    : 'Hola. Soy el asistente de MCP-INDUSTRIAL (motor de reglas de supervisión, me atiende el Agente Orquestador). Pregúntame por caudal, nivel, presión o temperatura.'}
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <div key={message.id} className={`msg msg-${message.role}`}>
                  <div className="msg-body">
                    {message.text}
                    {message.tools?.length || message.model ? (
                      <div className="msg-tools">
                        {message.model ? <span className="tag tag-warn">{message.model}</span> : null}
                        {message.tools?.map((tool) => (
                          <span key={tool.name} className={`tag ${tool.ok ? 'tag-ok' : 'tag-err'}`}>
                            {tool.name} · {tool.ms} ms
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))
            )}
            {busy ? (
              <div className="msg msg-agent">
                <div className="msg-body">…</div>
              </div>
            ) : null}
          </div>

          {failure ? (
            <div className="banner banner-err" style={{ marginBottom: 10 }}>
              {failure}
            </div>
          ) : null}

          <form
            className="chat-form"
            onSubmit={(event) => {
              event.preventDefault();
              void send(input);
            }}
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ej: ¿Cuál es la temperatura actual?"
              aria-label="Consulta al asistente"
            />
            <button type="submit" className="btn chat-send" disabled={busy || !input.trim()}>
              Enviar <IconArrow width="15" height="15" />
            </button>
          </form>
        </section>

        {/* Historial de acciones */}
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Historial de acciones</h2>
              <span className="panel-sub">Qué hizo cada agente y resultado</span>
            </div>
            <span className="tag">{actions.length} acción(es)</span>
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Hora</th>
                  <th>Agente</th>
                  <th>Qué hizo</th>
                  <th>Resultado</th>
                </tr>
              </thead>
              <tbody>
                {actions.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="empty">
                      Sin acciones registradas aún — aparecerán aquí las interacciones con los agentes.
                    </td>
                  </tr>
                ) : (
                  actions.map((action, index) => (
                    <tr key={`${action.ts}-${index}`}>
                      <td>{new Date(action.ts).toLocaleTimeString('es-PE', { hour12: false })}</td>
                      <td style={{ fontWeight: 700 }}>{action.agent}</td>
                      <td style={{ whiteSpace: 'normal', maxWidth: 320 }}>{action.what}</td>
                      <td>
                        <span className={`tag ${action.ok ? 'tag-ok' : 'tag-err'}`}>
                          {action.ok ? 'OK' : 'ERROR'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
