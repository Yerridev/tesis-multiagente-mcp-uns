import { useEffect, useMemo, useRef } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useNodesState,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeTypes,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import EquipoNode from './EquipoNode';
import PanelNode from './PanelNode';
import RelacionEdge from './RelacionEdge';
import type { LienzoEdge, MetaNodo } from './tipos';
import type { PanelLienzo } from '../pages/lienzo/nodos';

const nodeTypes: NodeTypes = { equipo: EquipoNode, panel: PanelNode };
const edgeTypes: EdgeTypes = { relacion: RelacionEdge };

/**
 * Posiciones guardadas por equipo: se conservan mientras se navega
 * (almacén a nivel de módulo, igual que el estado vivo del lienzo de la tesis).
 */
const POSICIONES: Record<string, Record<string, { x: number; y: number }>> = {};

/** Selección de lados de conexión — portada de VistaEquipo.tsx de la tesis. */
function lados(a: Node | undefined, b: Node | undefined): [string, string] {
  if (!a || !b) return ['s-right', 't-left'];
  const dx = b.position.x - a.position.x;
  const dy = b.position.y - a.position.y;
  if (Math.abs(dx) >= Math.abs(dy) * 1.2) return dx >= 0 ? ['s-right', 't-left'] : ['s-left', 't-right'];
  return dy >= 0 ? ['s-bottom', 't-top'] : ['s-top', 't-bottom'];
}

interface Props {
  equipoId: string;
  /** Metadatos estáticos de los nodos (posiciones del grafo). */
  metas: MetaNodo[];
  /** Relaciones del grafo (estables por equipo). */
  aristas: LienzoEdge[];
  /** Los 4 paneles (Diagnóstico/Agente/Tendencia/UNS) DENTRO del canvas, como en la tesis. */
  paneles: PanelLienzo[];
}

/**
 * Lienzo ReactFlow (idéntico comportamiento al de la tesis):
 * zoom con la rueda alrededor del cursor, desplazamiento con el fondo,
 * nodos arrastrables individualmente, Controls, MiniMap y fitView.
 * Los paneles son nodos `panel` del propio lienzo (se arrastran por su cabecera).
 */export default function VistaEquipo({ equipoId, metas, aristas, paneles }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const instancia = useRef<ReactFlowInstance | null>(null);

  /**
   * Los nodos se construyen UNA sola vez por equipo (como en la tesis):
   * así el arrastre nunca se interrumpe y las posiciones se conservan.
   * Los valores vivos llegan por contexto (Estado.lecturas).
   */
  useEffect(() => {
    const guardada = POSICIONES[equipoId] ?? {};
    const equipoNodes: Node[] = metas.map((meta) => ({
      id: meta.id,
      type: 'equipo',
      position: guardada[meta.id] ?? { x: meta.x, y: meta.y },
      data: { meta },
      style: { width: meta.w },
    }));
    /* Paneles del lienzo: nodos arrastrables por su cabecera (panel:* en el layout) */
    const panelNodes: Node[] = paneles.map((p) => ({
      id: `panel:${p.kind}`,
      type: 'panel',
      dragHandle: '.lz-panel-head',
      position: guardada[`panel:${p.kind}`] ?? { x: p.x, y: p.y },
      data: { kind: p.kind },
      style: { width: p.w, height: p.h },
    }));
    setNodes([...equipoNodes, ...panelNodes]);
  }, [metas, paneles, equipoId, setNodes]);

  const porId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);

  const edges: Edge[] = useMemo(
    () =>
      aristas.map((r) => {
        const [sh, th] = lados(porId[r.de], porId[r.a]);
        return {
          id: `${r.de}|${r.rel}|${r.a}`,
          source: r.de,
          target: r.a,
          sourceHandle: sh,
          targetHandle: th,
          type: 'relacion',
          data: { rel: r.rel, nota: r.nota },
        };
      }),
    [aristas, porId],
  );

  /* Guardar posición al soltar un nodo (se conserva al navegar) */
  const guardarPosicion = (_evento: unknown, node: Node) => {
    POSICIONES[equipoId] = POSICIONES[equipoId] ?? {};
    POSICIONES[equipoId][node.id] = { x: node.position.x, y: node.position.y };
  };

  return (
    <div className="lz-rf">
      <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
        <defs>
          <marker id="flecha-normal" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" className="flecha-normal" />
          </marker>
          <marker id="flecha-cadena" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" className="flecha-cadena" />
          </marker>
        </defs>
      </svg>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStop={guardarPosicion}
        onInit={(inst) => {
          instancia.current = inst;
        }}
        nodesDraggable={true}
        panOnDrag={true}
        zoomOnScroll={true}
        nodesConnectable={false}
        deleteKeyCode={null}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        minZoom={0.2}
        maxZoom={1.8}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeStrokeWidth={2}
          nodeColor={(n) => (n.type === 'panel' ? '#cfe0f5' : '#dfe7e2')}
          maskColor="rgba(33,33,33,0.06)"
        />
      </ReactFlow>

      {/* Leyenda fija en el visor (HTML, no escala) */}
      <div className="lz-leyenda-vp">
        <span>
          <i className="lz-l-flujo" /> flujo de proceso
        </span>
        <span>
          <i className="lz-l-rel" /> relación del grafo
        </span>
        <span>
          <i className="lz-l-cadena" /> cadena del diagnóstico
        </span>
        <span>
          <i className="lz-l-sin" /> sin dato disponible
        </span>
      </div>
    </div>
  );
}
