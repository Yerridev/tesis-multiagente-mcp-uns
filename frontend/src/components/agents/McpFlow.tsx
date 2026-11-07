import { useMemo } from 'react';
import { useNodosEstables } from './useNodosEstables';
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { AgentTool } from '../../types';

interface Datos extends Record<string, unknown> { titulo: string; sub?: string; estado?: string; tipo: 'servidor' | 'tool' }

function Nodo({ data }: NodeProps<Node<Datos>>) {
  return (
    <div className={`af-node ${data.tipo === 'servidor' ? 'af-servidor mf-srv' : 'mf-tool'}`}>
      <Handle type="target" position={Position.Left} className="af-handle" />
      <div className="af-head">
        {data.estado ? <span className={`srv-dot ${data.estado}`} /> : <span className="mf-ico">ƒ</span>}
        <b>{data.titulo}</b>
      </div>
      {data.sub ? <small className="af-sub">{data.sub}</small> : null}
      <Handle type="source" position={Position.Right} className="af-handle" />
    </div>
  );
}
const nodeTypes = { n: Nodo };

export interface ServidorMcp { key: string; name: string; desc: string; estado: string }

const ALTO_TOOL = 62;
const SEP = 40;

function Diagrama({ servidores, tools }: { servidores: ServidorMcp[]; tools: AgentTool[] }) {
  const { nodes: base, edges } = useMemo(() => {
    const nodes: Node<Datos>[] = [];
    const edges: Edge[] = [];
    let y = 0;
    for (const s of servidores) {
      const propias = tools.filter((t) => t.server === s.key);
      const alto = Math.max(1, propias.length) * ALTO_TOOL;
      nodes.push({ id: s.key, type: 'n', position: { x: 0, y: y + alto / 2 - 40 },
        data: { titulo: `Servidor MCP · ${s.name}`, sub: s.desc, estado: s.estado, tipo: 'servidor' } });
      propias.forEach((t, i) => {
        const id = `${s.key}:${t.name}`;
        nodes.push({ id, type: 'n', position: { x: 300, y: y + i * ALTO_TOOL }, data: { titulo: t.name, sub: t.description, tipo: 'tool' } });
        edges.push({ id: `e-${id}`, source: s.key, target: id, className: s.estado === 'ok' ? 'mf-edge-ok' : 'mf-edge' });
      });
      if (!propias.length) {
        const id = `${s.key}:vacio`;
        nodes.push({ id, type: 'n', position: { x: 300, y }, data: { titulo: 'sin herramientas publicadas', tipo: 'tool' } });
        edges.push({ id: `e-${id}`, source: s.key, target: id, className: 'mf-edge' });
      }
      y += alto + SEP;
    }
    return { nodes, edges };
  }, [servidores, tools]);

  const { nodes, onNodesChange, onNodeDragStop } = useNodosEstables('diagrama-servidores-mcp-v2', base);

  return (
    <ReactFlow nodes={nodes} onNodesChange={onNodesChange} onNodeDragStop={onNodeDragStop} nodesDraggable edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.08 }}
      nodesConnectable={false} elementsSelectable={false} proOptions={{ hideAttribution: true }} minZoom={0.3}>
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
  );
}

export function McpFlow(props: { servidores: ServidorMcp[]; tools: AgentTool[] }) {
  return (
    <div className="af-wrap mf-wrap">
      <ReactFlowProvider><Diagrama {...props} /></ReactFlowProvider>
    </div>
  );
}
