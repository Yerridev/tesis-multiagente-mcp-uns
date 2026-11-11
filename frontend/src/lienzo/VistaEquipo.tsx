import { useEffect, useMemo, useRef, useState } from 'react';
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
 * Posiciones guardadas por equipo: se conservan al navegar, al refrescar y al
 * cerrar el navegador (localStorage de este navegador). "Posición original" las borra.
 */
type Posiciones = Record<string, { x: number; y: number }>;
const POSICIONES: Record<string, Posiciones> = {};
const clave = (equipoId: string) => `mcp.lienzo.posiciones.${equipoId}`;

function leerPosiciones(equipoId: string): Posiciones {
  if (POSICIONES[equipoId]) return POSICIONES[equipoId];
  try {
    const crudo = localStorage.getItem(clave(equipoId));
    POSICIONES[equipoId] = crudo ? (JSON.parse(crudo) as Posiciones) : {};
  } catch {
    POSICIONES[equipoId] = {};
  }
  return POSICIONES[equipoId];
}

function guardarPosiciones(equipoId: string, pos: Posiciones) {
  POSICIONES[equipoId] = pos;
  try {
    if (Object.keys(pos).length === 0) localStorage.removeItem(clave(equipoId));
    else localStorage.setItem(clave(equipoId), JSON.stringify(pos));
  } catch {
    /* sin almacenamiento: se conserva solo mientras la pestaña esté abierta */
  }
}

/* Lado de salida/entrada elegido a mano para cada flecha (id de la arista -> handles) */
type Lados = Record<string, { s?: string; t?: string }>;
const claveLados = (equipoId: string) => `mcp.lienzo.lados.${equipoId}`;
function leerLados(equipoId: string): Lados {
  try {
    const crudo = localStorage.getItem(claveLados(equipoId));
    return crudo ? (JSON.parse(crudo) as Lados) : {};
  } catch {
    return {};
  }
}
function guardarLados(equipoId: string, l: Lados) {
  try {
    if (Object.keys(l).length === 0) localStorage.removeItem(claveLados(equipoId));
    else localStorage.setItem(claveLados(equipoId), JSON.stringify(l));
  } catch {
    /* sin almacenamiento */
  }
}
const LADOS_UI: { k: string; ico: string; t: string }[] = [
  { k: 'top', ico: '↑', t: 'arriba' },
  { k: 'right', ico: '→', t: 'derecha' },
  { k: 'bottom', ico: '↓', t: 'abajo' },
  { k: 'left', ico: '←', t: 'izquierda' },
];

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
  const [version, setVersion] = useState(0);   // sube al pulsar "Posición original"
  const [ladosOv, setLadosOv] = useState<Lados>(() => leerLados(equipoId));
  const [editando, setEditando] = useState<{ id: string; x: number; y: number } | null>(null);
  const caja = useRef<HTMLDivElement | null>(null);
  useEffect(() => { setLadosOv(leerLados(equipoId)); setEditando(null); }, [equipoId]);

  useEffect(() => {
    const guardada = leerPosiciones(equipoId);
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
  }, [metas, paneles, equipoId, setNodes, version]);

  const porId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);

  const edges: Edge[] = useMemo(
    () =>
      aristas.map((r) => {
        const id = `${r.de}|${r.rel}|${r.a}`;
        const [autoS, autoT] = lados(porId[r.de], porId[r.a]);
        const sh = ladosOv[id]?.s ?? autoS;
        const th = ladosOv[id]?.t ?? autoT;
        return {
          id,
          source: r.de,
          target: r.a,
          sourceHandle: sh,
          targetHandle: th,
          type: 'relacion',
          data: { rel: r.rel, nota: r.nota },
        };
      }),
    [aristas, porId, ladosOv],
  );

  /* Elegir por qué lado sale / entra una flecha (se guarda en el navegador) */
  const fijarLado = (id: string, extremo: 's' | 't', lado: string | null) => {
    setLadosOv((prev) => {
      const actual = { ...(prev[id] ?? {}) };
      if (lado) actual[extremo] = `${extremo}-${lado}`;
      else delete actual[extremo];
      const sig = { ...prev };
      if (actual.s || actual.t) sig[id] = actual;
      else delete sig[id];
      guardarLados(equipoId, sig);
      return sig;
    });
  };
  const nombreNodo = (id: string) => {
    const n = (porId[id]?.data as { meta?: MetaNodo } | undefined)?.meta?.nombre ?? id;
    return n.length > 26 ? `${n.slice(0, 25)}…` : n;
  };
  const aristaEdit = editando ? edges.find((e) => e.id === editando.id) : undefined;

  /* Guardar posición al soltar uno o varios nodos (se conserva al refrescar) */
  const guardarPosicion = (_evento: unknown, node: Node, movidos?: Node[]) => {
    const pos = { ...leerPosiciones(equipoId) };
    for (const n of movidos && movidos.length ? movidos : [node]) {
      pos[n.id] = { x: Math.round(n.position.x), y: Math.round(n.position.y) };
    }
    guardarPosiciones(equipoId, pos);
  };

  const posicionOriginal = () => {
    guardarPosiciones(equipoId, {});
    guardarLados(equipoId, {});
    setLadosOv({});
    setEditando(null);
    setVersion((v) => v + 1);
    window.setTimeout(() => instancia.current?.fitView({ padding: 0.08, duration: 300 }), 50);
  };

  return (
    <div className="lz-rf" ref={caja}>
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
        onEdgeClick={(ev, edge) => {
          const r = caja.current?.getBoundingClientRect();
          setEditando({ id: edge.id, x: ev.clientX - (r?.left ?? 0), y: ev.clientY - (r?.top ?? 0) });
        }}
        onPaneClick={() => setEditando(null)}
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

      {editando && aristaEdit ? (
        <div className="lz-lados" style={{ left: editando.x + 12, top: editando.y + 12 }} onClick={(e) => e.stopPropagation()}>
          <div className="lz-lados-tit">
            <span>{nombreNodo(aristaEdit.source)} → {nombreNodo(aristaEdit.target)}</span>
            <button type="button" className="lz-lados-x" onClick={() => setEditando(null)} aria-label="Cerrar">×</button>
          </div>
          {(['s', 't'] as const).map((ext) => {
            const actual = (ext === 's' ? aristaEdit.sourceHandle : aristaEdit.targetHandle) ?? '';
            const manual = ladosOv[aristaEdit.id]?.[ext];
            return (
              <div className="lz-lados-fila" key={ext}>
                <span>{ext === 's' ? 'Sale por' : 'Entra por'}</span>
                {LADOS_UI.map((l) => (
                  <button key={l.k} type="button" title={l.t}
                    className={actual === `${ext}-${l.k}` ? (manual ? 'on manual' : 'on') : ''}
                    onClick={() => fijarLado(aristaEdit.id, ext, l.k)}>{l.ico}</button>
                ))}
                <button type="button" className={manual ? 'auto' : 'auto on'} title="Elegir automáticamente"
                  onClick={() => fijarLado(aristaEdit.id, ext, null)}>Auto</button>
              </div>
            );
          })}
        </div>
      ) : null}

      <button type="button" className="lz-pos-original" onClick={posicionOriginal} title="Vuelve a colocar los nodos y paneles como vienen por defecto">
        ↺ Posición original
      </button>

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
