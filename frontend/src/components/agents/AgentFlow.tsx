import { useMemo } from 'react';
import { useNodosEstables } from './useNodosEstables';
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

/** Estado visual de cada nodo: ok (verde) · busy (naranja) · err (rojo) · pending (gris). */
export type EstadoNodo = 'ok' | 'busy' | 'err' | 'pending';

interface DatosNodo extends Record<string, unknown> {
  titulo: string;
  sub?: string;
  tarea?: string;
  estado: EstadoNodo;
  activo: boolean;
  tipo: 'usuario' | 'agente' | 'servidor' | 'llm';
}

function NodoAgente({ data }: NodeProps<Node<DatosNodo>>) {
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
}

/* Posiciones fijas (x, y) del diagrama */
const POS: Record<string, [number, number]> = {
  usuario: [300, 0],
  orquestador: [300, 120],
  llm: [620, 120],
  ingesta: [0, 280], validacion: [215, 280], analisis: [430, 280], reportes: [645, 280],
  'srv-rt': [105, 460], 'srv-hist': [430, 460], 'srv-traz': [645, 460],
};

const SERVIDORES = [
  { key: 'srv-rt', titulo: 'Servidor MCP · Tiempo real', sub: 'SignalR /hubs/plant · /api/equipment' },
  { key: 'srv-hist', titulo: 'Servidor MCP · Histórico y análisis', sub: '/api/history · PostgreSQL' },
  { key: 'srv-traz', titulo: 'Servidor MCP · Trazabilidad', sub: 'auditoría de acciones' },
];

const USA: Record<string, string[]> = {
  ingesta: ['srv-rt'], validacion: ['srv-rt'], analisis: ['srv-hist'], reportes: ['srv-hist', 'srv-traz'],
};

function Diagrama({ agentes, estado, tarea, activos, ocupado, llm }: Props) {
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
          titulo: a.name.startsWith('Agente') ? a.name : `Agente ${a.name}`, sub: a.key === 'orquestador' ? 'Delega el trabajo' : undefined,
          tarea: tarea(a.name), estado: estado(a.key) as EstadoNodo,
          activo: activos.has(a.key) || (a.key === 'orquestador' && ocupado), tipo: 'agente',
        },
      });
    }
    for (const s of SERVIDORES) {
      n.push({
        id: s.key, type: 'agente', position: { x: POS[s.key][0], y: POS[s.key][1] },
        data: { titulo: s.titulo, sub: s.sub, estado: 'ok', activo: activos.has(s.key), tipo: 'servidor' },
      });
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
  }, [agentes, estado, tarea, activos, ocupado, llm]);

  const edges = useMemo<Edge[]>(() => {
    const llmOn = llm.activo && ocupado;
    const e: Edge[] = [
      { id: 'u-o', source: 'usuario', target: 'orquestador', animated: ocupado, className: ocupado ? 'af-edge-on' : '' },
      { id: 'o-llm', source: 'orquestador', sourceHandle: 'der', target: 'llm', targetHandle: 'izq', animated: llmOn,
        label: llm.activo ? 'API externa' : 'desconectado', className: llmOn ? 'af-edge-on' : llm.activo ? '' : 'af-edge-off' },
    ];
    for (const a of agentes) {
      if (a.key === 'orquestador') continue;
      const on = activos.has(a.key);
      e.push({ id: `o-${a.key}`, source: 'orquestador', target: a.key, animated: on, className: on ? 'af-edge-on' : '' });
      for (const s of USA[a.key] ?? []) {
        const on2 = on && activos.has(s);
        e.push({ id: `${a.key}-${s}`, source: a.key, target: s, animated: on2, className: on2 ? 'af-edge-on' : '' });
      }
    }
    return e;
  }, [agentes, activos, ocupado, llm]);

  const { nodes, onNodesChange, onNodeDragStop } = useNodosEstables('diagrama-agentes-v2', base);

  return (
    <ReactFlow nodes={nodes} onNodesChange={onNodesChange} onNodeDragStop={onNodeDragStop} nodesDraggable edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.12 }}
      nodesConnectable={false} elementsSelectable={false} proOptions={{ hideAttribution: true }} minZoom={0.3}>
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}

export function AgentFlow(props: Props) {
  return (
    <div className="af-wrap">
      <ReactFlowProvider>
        <Diagrama {...props} />
      </ReactFlowProvider>
    </div>
  );
}
