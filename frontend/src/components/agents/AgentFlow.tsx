import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useNodosEstables } from './useNodosEstables';
import { Background, BackgroundVariant, ControlButton, Controls, Handle, Position, ReactFlow, ReactFlowProvider, useReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

/** Estado visual de cada nodo: ok (verde) · busy (naranja) · err (rojo) · pending (gris). */
export type EstadoNodo = 'ok' | 'busy' | 'err' | 'pending';

interface DatosNodo extends Record<string, unknown> {
  titulo: string;
  sub?: string;
  tarea?: string;
  estado: EstadoNodo;
  activo: boolean;
  tipo: 'usuario' | 'agente' | 'servidor' | 'llm' | 'herramienta';
}

function NodoAgente({ data }: NodeProps<Node<DatosNodo>>) {
  if (data.tipo === 'herramienta')
    return (
      <div className={`af-node af-herramienta${data.activo ? ' af-activo' : ''}`} title={data.sub}>
        <Handle type="target" id="izq" position={Position.Left} className="af-handle" />
        <span className="mf-ico">ƒ</span> <b>{data.titulo}</b>
      </div>
    );
  return (
    <div className={`af-node af-${data.tipo}${data.activo ? ' af-activo' : ''}`}>
      <Handle type="target" position={Position.Top} className="af-handle" />
      <div className="af-head">
        <span className={`srv-dot ${data.estado}`} />
        <b>{data.titulo}</b>
      </div>
      {data.sub ? <small className="af-sub">{data.sub}</small> : null}
      {data.tarea ? <div className={`af-tarea${data.tarea.startsWith('Sin') ? ' is-empty' : ''}`}>{data.tarea}</div> : null}
      <Handle type="source" position={Position.Bottom} className="af-handle" />
      <Handle type="source" id="der" position={Position.Right} className="af-handle" />
      <Handle type="target" id="izq" position={Position.Left} className="af-handle" />
    </div>
  );
}

const nodeTypes = { agente: NodoAgente };

export interface AgenteFlujo {
  key: string;
  name: string;
  server: string;
}

interface Props {
  agentes: AgenteFlujo[];
  estado: (key: string) => string;
  tarea: (name: string) => string;
  activos: Set<string>;     // claves de agentes/servidores trabajando ahora
  ocupado: boolean;         // el orquestador esta procesando una pregunta
  llm: { activo: boolean; modelo?: string | null };  // modelo de lenguaje (OpenRouter en la nube)
  verServidores: boolean;      // casilla "Servidores MCP"
  verHerramientas: boolean;    // casilla "Herramientas"
  /** herramientas publicadas por cada servidor (list_tools real), clave = 'mcp-nivel'… */
  herramientas: Record<string, { nombre: string; descripcion: string }[]>;
  /** casillas (Servidores MCP / Herramientas) que también se muestran en la vista ampliada */
  controles?: ReactNode;
  /** si se pasa, la ampliación la maneja la página (sin ventana emergente propia) */
  onAmpliar?: () => void;
  ampliado?: boolean;
}

/* Posiciones fijas (x, y): operador → orquestador → 4 analistas → 4 servidores MCP (uno por módulo) */
const POS: Record<string, [number, number]> = {
  usuario: [435, 0],
  orquestador: [435, 120],
  llm: [800, 120],
  'analista-nivel': [0, 290], 'analista-caudal': [290, 290], 'analista-presion': [580, 290], 'analista-temperatura': [870, 290],
  'mcp-nivel': [0, 460], 'mcp-caudal': [290, 460], 'mcp-presion': [580, 460], 'mcp-temperatura': [870, 460],
};

const SERVIDORES = [
  { key: 'mcp-nivel', titulo: 'Servidor MCP · Nivel', sub: ':8001 · 7 herramientas · solo lectura' },
  { key: 'mcp-caudal', titulo: 'Servidor MCP · Caudal', sub: ':8002 · 7 herramientas · solo lectura' },
  { key: 'mcp-presion', titulo: 'Servidor MCP · Presión', sub: ':8003 · 7 herramientas · solo lectura' },
  { key: 'mcp-temperatura', titulo: 'Servidor MCP · Temperatura', sub: ':8004 · 7 herramientas · solo lectura' },
];

const USA: Record<string, string[]> = {
  'analista-nivel': ['mcp-nivel'], 'analista-caudal': ['mcp-caudal'],
  'analista-presion': ['mcp-presion'], 'analista-temperatura': ['mcp-temperatura'],
};

function Diagrama({ agentes, estado, tarea, activos, ocupado, llm, verServidores, verHerramientas, herramientas, ampliado, onAmpliar }: Props & { ampliado: boolean; onAmpliar: () => void }) {
  const base = useMemo<Node<DatosNodo>[]>(() => {
    const n: Node<DatosNodo>[] = [
      {
        id: 'usuario', type: 'agente', position: { x: POS.usuario[0], y: POS.usuario[1] }, draggable: true,
        data: { titulo: 'Operador', sub: 'Pregunta desde el chat', estado: ocupado ? 'busy' : 'ok', activo: ocupado, tipo: 'usuario' },
      },
    ];
    for (const a of agentes) {
      const [x, y] = POS[a.key] ?? [0, 0];
      n.push({
        id: a.key, type: 'agente', position: { x, y },
        data: {
          titulo: a.name.startsWith('Agente') ? a.name : `Agente ${a.name}`, sub: a.key === 'orquestador' ? 'Intérprete + veredicto' : 'Analista · usa su servidor MCP',
          tarea: tarea(a.name), estado: estado(a.key) as EstadoNodo,
          activo: activos.has(a.key) || (a.key === 'orquestador' && ocupado), tipo: 'agente',
        },
      });
    }
    for (const s of verServidores ? SERVIDORES : []) {
      const [sx, sy] = POS[s.key];
      n.push({
        id: s.key, type: 'agente', position: { x: sx, y: sy },
        data: { titulo: s.titulo, sub: s.sub, estado: estado(s.key) as EstadoNodo, activo: activos.has(s.key), tipo: 'servidor' },
      });
      /* herramientas del servidor en lista vertical debajo de él */
      for (const [i, h] of (verHerramientas ? herramientas[s.key] ?? [] : []).entries()) {
        const id = `${s.key}:${h.nombre}`;
        n.push({
          id, type: 'agente', position: { x: sx + 28, y: sy + 95 + i * 40 },
          data: { titulo: h.nombre, sub: h.descripcion, estado: estado(s.key) as EstadoNodo, activo: activos.has(id), tipo: 'herramienta' },
        });
      }
    }
    n.push({
      id: 'llm', type: 'agente', position: { x: POS.llm[0], y: POS.llm[1] },
      data: {
        titulo: 'LLM · OpenRouter (nube)',
        sub: llm.activo ? (llm.modelo ?? 'modelo en la nube') : 'Sin conexión · usa motor de reglas',
        tarea: llm.activo ? 'Conexión externa HTTPS' : 'Sin OPENROUTER_API_KEY',
        estado: llm.activo ? (ocupado ? 'busy' : 'ok') : 'pending',
        activo: llm.activo && ocupado, tipo: 'llm',
      },
    });
    return n;
  }, [agentes, estado, tarea, activos, ocupado, llm, verServidores, verHerramientas, herramientas]);

  const edges = useMemo<Edge[]>(() => {
    const llmOn = llm.activo && ocupado;
    const e: Edge[] = [
      { id: 'u-o', source: 'usuario', target: 'orquestador', animated: ocupado, className: ocupado ? 'af-edge-on' : '' },
      { id: 'o-llm', source: 'orquestador', sourceHandle: 'der', target: 'llm', targetHandle: 'izq', animated: llmOn,
        label: llm.activo ? 'OpenRouter' : 'desconectado', className: llmOn ? 'af-edge-on' : llm.activo ? '' : 'af-edge-off' },
    ];
    for (const a of agentes) {
      if (a.key === 'orquestador') continue;
      const on = activos.has(a.key);
      e.push({ id: `o-${a.key}`, source: 'orquestador', target: a.key, animated: on, label: on ? 'MQTT' : undefined, className: on ? 'af-edge-on' : '' });
      for (const s of verServidores ? USA[a.key] ?? [] : []) {
        const on2 = on && activos.has(s);
        e.push({ id: `${a.key}-${s}`, source: a.key, target: s, animated: on2, className: on2 ? 'af-edge-on' : '' });
        for (const h of verHerramientas ? herramientas[s] ?? [] : []) {
          const id = `${s}:${h.nombre}`;
          const on3 = activos.has(id);
          e.push({ id: `${s}-${id}`, source: s, target: id, targetHandle: 'izq', type: 'smoothstep', animated: on3, className: on3 ? 'af-edge-on' : 'af-edge-tool' });
        }
      }
    }
    return e;
  }, [agentes, activos, ocupado, llm, verServidores, verHerramientas, herramientas]);

  const { nodes, onNodesChange, onNodeDragStop } = useNodosEstables('diagrama-agentes-v3', base);

  /* al mostrar/ocultar servidores o herramientas cambia el tamaño del diagrama: se vuelve a encuadrar */
  const rf = useReactFlow();
  useEffect(() => {
    const id = window.setTimeout(() => void rf.fitView({ padding: 0.12, duration: 250 }), 80);
    return () => window.clearTimeout(id);
  }, [nodes.length, rf]);

  return (
    <ReactFlow nodes={nodes} onNodesChange={onNodesChange} onNodeDragStop={onNodeDragStop} nodesDraggable edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.12 }}
      nodesConnectable={false} elementsSelectable={false} proOptions={{ hideAttribution: true }} minZoom={0.3}>
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
      <Controls showInteractive={false}>
        <ControlButton onClick={onAmpliar} title={ampliado ? 'Cerrar vista ampliada (Esc)' : 'Agrandar el diagrama'} aria-label={ampliado ? 'Cerrar vista ampliada' : 'Agrandar el diagrama'}>
          {ampliado ? (
            /* contraer: ventana grande abajo-izquierda, pequeña arriba-derecha */
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2.5" y="8.5" width="14" height="12" /><rect x="13.5" y="3.5" width="8" height="7" /></svg>
          ) : (
            /* agrandar: ventana pequeña abajo-izquierda que pasa a la grande arriba-derecha */
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2"><rect x="7.5" y="3.5" width="14" height="12" /><rect x="2.5" y="12.5" width="8" height="8" /></svg>
          )}
        </ControlButton>
      </Controls>
    </ReactFlow>
  );
}

export function AgentFlow(props: Props) {
  const [ampliado, setAmpliado] = useState(false);
  /* Esc cierra la vista ampliada */
  useEffect(() => {
    if (!ampliado) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setAmpliado(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ampliado]);

  if (props.onAmpliar)
    return (
      <div className={`af-wrap${props.ampliado ? ' af-modal-lienzo' : ''}`}>
        <ReactFlowProvider>
          <Diagrama {...props} ampliado={props.ampliado ?? false} onAmpliar={props.onAmpliar} />
        </ReactFlowProvider>
      </div>
    );


  return (
    <>
      <div className="af-wrap">
        <ReactFlowProvider>
          <Diagrama {...props} ampliado={false} onAmpliar={() => setAmpliado(true)} />
        </ReactFlowProvider>
      </div>
      {ampliado
        ? createPortal(
            <div className="af-modal-fondo" onClick={() => setAmpliado(false)}>
              <div className="af-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Sistema multiagente MCP ampliado">
                <div className="af-modal-cab">
                  <b>Sistema multiagente MCP</b>
                  <div className="af-modal-der">
                  {props.controles}
                  <button type="button" className="af-modal-cerrar" onClick={() => setAmpliado(false)} title="Cerrar (Esc)" aria-label="Cerrar">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
                  </button>
                  </div>
                </div>
                <div className="af-wrap af-modal-lienzo">
                  <ReactFlowProvider>
                    <Diagrama {...props} ampliado onAmpliar={() => setAmpliado(false)} />
                  </ReactFlowProvider>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
