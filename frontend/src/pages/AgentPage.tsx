import { useEffect, useMemo, useRef, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { api } from '../services/api';
import type { AgentCall, AgentStatus } from '../types';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { IconArrow } from '../components/common/Icons';
import { AgentFlow } from '../components/agents/AgentFlow';
import { SelectorModelo, useModeloElegido } from '../components/agents/SelectorModelo';
import { CajaChat } from '../components/agents/CajaChat';
import { HistorialChats } from '../components/agents/HistorialChats';
import { useSesion } from '../components/agents/useSesion';
import type { ConversacionCompleta } from '../types';
import { TextoMd } from '../components/agents/TextoMd';

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

/* Sistema multiagente MCP (Python, bat 31): orquestador + un analista por módulo, cada uno con su servidor MCP */
const AGENTES = [
  { key: 'orquestador', name: 'Agente Orquestador', desc: 'Intérprete: reparte la pregunta · Veredicto: integra los informes', server: 'Ninguno directo (coordina por MQTT)' },
  { key: 'analista-nivel', name: 'Analista de Nivel', desc: 'Analiza el módulo MCN-09 (MicroLogix)', server: 'Servidor MCP · Nivel :8001' },
  { key: 'analista-caudal', name: 'Analista de Caudal', desc: 'Analiza el módulo MCC-09 (S7-200)', server: 'Servidor MCP · Caudal :8002' },
  { key: 'analista-presion', name: 'Analista de Presión', desc: 'Analiza el módulo MCP-09 (cFP-2200)', server: 'Servidor MCP · Presión :8003' },
  { key: 'analista-temperatura', name: 'Analista de Temperatura', desc: 'Analiza el módulo MCT-09 (Twido)', server: 'Servidor MCP · Temperatura :8004' },
];
const NOMBRE: Record<string, string> = Object.fromEntries(AGENTES.map((a) => [a.key, a.name]));

/** Traza → agente: "interprete"/"veredicto" = orquestador · "analista-x" y "mcp-x.herramienta" = analista x. */
function agenteDe(tool: string): string {
  const m = /^(?:analista|mcp)-(nivel|caudal|presion|temperatura)/.exec(tool);
  return m ? `analista-${m[1]}` : 'orquestador';
}

const AGENT_KEY = (key: string) => `mcp-agente-${key}`;

export function AgentPage() {
  const { link, health, load, error, reload } = usePlant();
  /* el chat se conserva al cambiar de módulo o refrescar; se borra con "Nuevo chat" o al cerrar el navegador */
  const [messages, setMessages] = useSesion<ChatMessage[]>('mcp.chat.agentes.mensajes', []);
  const [actions, setActions] = useSesion<Action[]>('mcp.chat.agentes.acciones', []);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const ia = useModeloElegido(status);   // modelo elegido junto a Enviar
  const [activos, setActivos] = useState<Set<string>>(new Set());
  const apagar = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(messages.reduce((m, x) => Math.max(m, x.id), 0) + 1);
  const [convId, setConvId] = useSesion<string | null>('mcp.chat.agentes.conversacion', null);   // conversación guardada en curso
  const [historialAbierto, setHistorialAbierto] = useState(false);

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
    if (key === 'orquestador') return busy ? 'busy' : multi ? 'ok' : health === 'error' ? 'err' : 'pending';
    if (busy && activos.has(key)) return 'busy';
    return multi ? (link === 'disconnected' ? 'err' : 'ok') : 'pending';
  };

  const lastTask = (agentName: string) => {
    const found = actions.find((a) => a.agent === agentName);
    if (!found) return agentName === 'Agente Orquestador' ? 'Sin tareas aún' : 'Sin tareas registradas';
    return found.what;
  };

  const llm = status?.mode === 'llm';
  const multi = status?.multiagente === true;
  const modeText = multi
    ? `Sistema multiagente MCP · 5 agentes · 4 servidores MCP · ${ia.actual?.nombre ?? status?.model}`
    : llm
      ? `Agente clásico (abre el bat 31 para el multiagente) · ${ia.actual?.nombre ?? status?.model}`
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
      const historial = messages.map((m) => ({ rol: m.role === 'user' ? ('user' as const) : ('agente' as const), texto: m.text }));
      const reply = await api.agentAsk(message, ia.modelo, historial, { id: convId, origen: 'agentes' });
      if (reply.conversacionId) setConvId(reply.conversacionId);
      setMessages((prev) => [...prev, { id: nextId.current++, role: 'agent', text: reply.reply, tools: reply.tools, model: reply.model ?? null }]);
      {
        const on = new Set<string>(['orquestador']);
        for (const tool of reply.tools) {
          const key = agenteDe(tool.name);
          on.add(key);
          if (tool.name.startsWith('mcp-')) on.add(tool.name.split('.')[0]);
        }
        setActivos(on);
        if (apagar.current) clearTimeout(apagar.current);
        apagar.current = setTimeout(() => setActivos(new Set()), 6000);
      }
      setActions((prev) => {
        const rows: Action[] = reply.tools.map((tool) => ({
          ts: reply.ts,
          agent: NOMBRE[agenteDe(tool.name)],
          what: `${tool.name}${tool.result ? `: ${tool.result}` : ''}${tool.ms ? ` · ${tool.ms} ms` : ''}`,
          ok: tool.ok,
        }));
        rows.push({
          ts: reply.ts,
          agent: 'Agente Orquestador',
          what: `Respondió a: «${message}»${reply.mode === 'multiagente' ? ' · sistema multiagente' : ''}`,
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

  const nuevoChat = () => { setMessages([]); setActions([]); setConvId(null); setFailure(null); };
  const continuar = (c: ConversacionCompleta) => {
    setConvId(c.id);
    setMessages(c.mensajes.map((m) => ({ id: nextId.current++, role: m.rol === 'user' ? 'user' : 'agent', text: m.texto, tools: m.herramientas ?? undefined, model: m.modelo ?? null })));
  };

  if (load === 'loading') return <LoadingBlock label="Preparando los agentes de IA…" />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  return (
    <div className="agents-view">
      <div className="agents-grid">
        {/* Historial de acciones */}
        <section className="panel ag-hist">
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
        {/* Agentes de IA en tiempo real (diagrama de nodos) */}
        <section className="panel ag-flow">
          <div className="panel-head">
            <div>
              <h2>Sistema multiagente MCP</h2>
              <span className="panel-sub">{multi ? 'En línea' : 'Fuera de línea (bat 31)'} · rojo = trabajando ahora</span>
            </div>
          </div>
          <AgentFlow agentes={AGENTES} estado={dotState} tarea={lastTask} activos={activos} ocupado={busy}
            llm={{ activo: llm, modelo: ia.modelo ?? status?.model }} />
        </section>

        {/* Chat (atendido por el Agente Orquestador) */}
        <section className="panel panel-chat ag-chat">
          <div className="panel-head">
            <div>
              <h2>Asistente de agentes IA</h2>
              <span className="panel-sub" id="chatStatus">
                {busy ? (multi ? 'Los agentes están analizando sus módulos…' : llm ? 'Consultando la IA…' : 'Consultando el asistente…') : modeText}
              </span>
            </div>
            <div className="hc-acciones">
              <button type="button" className="hc-btn" onClick={() => setHistorialAbierto(true)} title="Ver conversaciones guardadas">Historial</button>
              <button type="button" className="hc-btn" onClick={nuevoChat} disabled={busy || messages.length === 0} title="Empezar una conversación nueva">Nuevo chat</button>
            </div>
            {multi ? (
              <span className="pill pill-ok pill-live">
                <i />
                MULTIAGENTE
              </span>
            ) : llm ? (
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
                  {multi
                    ? 'Hola. Te atiende el sistema multiagente MCP: el orquestador interpreta tu pregunta, los analistas de nivel, caudal, presión y temperatura consultan su servidor MCP y el veredicto integra todo. Solo lectura: no doy órdenes al PLC.'
                    : llm
                    ? 'Hola. Soy el asistente de MCP-INDUSTRIAL (IA vía OpenRouter, me atiende el Agente Orquestador). Pregúntame por caudal, nivel, presión o temperatura: respondo con los datos en vivo de la planta.'
                    : 'Hola. Soy el asistente de MCP-INDUSTRIAL (motor de reglas de supervisión, me atiende el Agente Orquestador). Pregúntame por caudal, nivel, presión o temperatura.'}
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <div key={message.id} className={`msg msg-${message.role}`}>
                  <div className="msg-body">
                    {message.role === 'agent' ? <TextoMd texto={message.text} /> : message.text}
                    {message.tools?.length || message.model ? (
                      <div className="msg-tools">
                        {message.model ? <span className="tag tag-warn">{message.model}</span> : null}
                        {message.tools?.map((tool, i) => (
                          <span key={`${tool.name}-${i}`} className={`tag ${tool.ok ? 'tag-ok' : 'tag-err'}`}>
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

          <HistorialChats abierto={historialAbierto} onCerrar={() => setHistorialAbierto(false)} onContinuar={continuar} />
          <div className="chat-pie">
          {failure ? (
            <div className="banner banner-err" style={{ marginBottom: 10 }}>
              {failure}
            </div>
          ) : null}

          <CajaChat
            valor={input}
            onCambio={setInput}
            onEnviar={() => void send(input)}
            placeholder="Ej: ¿Cuál es la temperatura actual?"
            etiqueta="Consulta al asistente"
            ocupado={busy}
            extras={llm ? <SelectorModelo modelos={ia.modelos} valor={ia.modelo} onElegir={ia.elegir} disabled={busy} /> : null}
            textoBoton={<>Enviar <IconArrow width="15" height="15" /></>}
          />
          </div>
        </section>

      </div>


    </div>
  );
}
