import { Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

/* Arquitectura multiagente MCP-UNS implementada (6 capas + monitoreo + seguridad), replicada con nodos. */

type Tono = 'c6' | 'c5' | 'c4' | 'c3' | 'c2' | 'c1' | 'mon' | 'seg' | 'llm';

interface Capa extends Record<string, unknown> { num?: string; titulo: string; sub?: string; tono: Tono; w: number; h: number }
interface Caja extends Record<string, unknown> { titulo: string; sub?: string; items?: string[]; tono: Tono; w?: number }

function NodoCapa({ data }: NodeProps<Node<Capa>>) {
  return (
    <div className={`al-capa al-${data.tono}`} style={{ width: data.w, height: data.h }}>
      {data.num ? <span className="al-num">{data.num}</span> : null}
      <div className="al-capa-txt">
        <b>{data.titulo}</b>
        {data.sub ? <small>{data.sub}</small> : null}
      </div>
    </div>
  );
}

function NodoCaja({ data }: NodeProps<Node<Caja>>) {
  return (
    <div className={`al-caja al-b-${data.tono}`} style={{ width: data.w ?? 200 }}>
      <Handle type="target" position={Position.Top} className="af-handle" />
      <Handle type="target" id="izq" position={Position.Left} className="af-handle" />
      <b>{data.titulo}</b>
      {data.sub ? <small>{data.sub}</small> : null}
      {data.items?.length ? <ul>{data.items.map((i) => <li key={i}>{i}</li>)}</ul> : null}
      <Handle type="source" position={Position.Bottom} className="af-handle" />
      <Handle type="source" id="der" position={Position.Right} className="af-handle" />
      <Handle type="source" id="arr" position={Position.Top} className="af-handle" />
      <Handle type="target" id="aba" position={Position.Bottom} className="af-handle" />
    </div>
  );
}

const nodeTypes = { capa: NodoCapa, caja: NodoCaja };

const ANCHO = 1560;
const X0 = 250;          // inicio de las cajas (despues del titulo de la capa)

const capa = (id: string, y: number, h: number, num: string, titulo: string, sub: string, tono: Tono): Node<Capa> => ({
  id, type: 'capa', position: { x: 0, y }, data: { num, titulo, sub, tono, w: ANCHO, h },
  draggable: false, selectable: false, zIndex: -1,
});

/** Reparte cajas en una fila de la capa. */
function fila(y: number, tono: Tono, cajas: { id: string; titulo: string; sub?: string; items?: string[]; w?: number }[], x = X0, gap = 14, w?: number): Node<Caja>[] {
  const ancho = w ?? Math.floor((ANCHO - x - 20 - gap * (cajas.length - 1)) / cajas.length);
  return cajas.map((c, i) => ({ id: c.id, type: 'caja', position: { x: x + i * (ancho + gap), y }, data: { ...c, tono, w: c.w ?? ancho } }));
}

const nodes: Node[] = [
  // ---- capas ----
  capa('L6', 0, 150, '6', 'Interfaz de usuario', '(ingeniero o analista)', 'c6'),
  capa('L5', 190, 200, '5', 'Orquestación multiagente de IA', '(agentes especializados)', 'c5'),
  capa('L4', 430, 190, '4', 'Servidores MCP', '(por equipo industrial)', 'c4'),
  capa('L3', 660, 170, '3', 'Integración UNS y persistencia', '(broker, ingestores y BD)', 'c3'),
  capa('L2', 870, 120, '2', 'Adaptadores industriales Edge', '(conectores de solo lectura)', 'c2'),
  capa('L1', 1030, 110, '1', 'Fuentes de datos industriales', '(equipos reales integrados)', 'c1'),

  // ---- 6 interfaz ----
  ...fila(25, 'c6', [
    { id: 'ui-lienzo', titulo: 'Lienzo industrial interactivo' },
    { id: 'ui-vista', titulo: 'Vista general y por equipo' },
    { id: 'ui-chat', titulo: 'Panel de conversación multiagente' },
    { id: 'ui-tend', titulo: 'Tendencias históricas' },
    { id: 'ui-diag', titulo: 'Diagnóstico y reportes' },
    { id: 'ui-uns', titulo: 'Visualización del UNS' },
  ], X0, 12, 128),
  { id: 'ui-canales', type: 'caja', position: { x: 1100, y: 15 }, data: { titulo: 'Canales de comunicación', tono: 'c6', w: 440,
    items: ['REST → consultas normales', 'WebSocket → datos MQTT en vivo', 'SSE → eventos y resultados'] } },

  // ---- 5 orquestacion ----
  { id: 'coord', type: 'caja', position: { x: 520, y: 205 }, data: { titulo: 'Agente coordinador', tono: 'c5', w: 420,
    sub: 'Planificador determinista y auditable (consolida resultados, sin herramientas directas)' } },
  { id: 'llm', type: 'caja', position: { x: 1060, y: 200 }, data: { titulo: 'LLM configurable', tono: 'llm', w: 480,
    sub: 'OpenRouter (en uso, nube) · Gemini · Anthropic · API compatible con OpenAI' } },
  ...fila(300, 'c5', [
    { id: 'ag-consulta', titulo: 'Agente de consulta industrial', sub: 'Consultas de datos actuales e históricos' },
    { id: 'ag-diag', titulo: 'Agente de diagnóstico industrial', sub: 'Análisis, coherencia y diagnóstico causal' },
    { id: 'ag-rep', titulo: 'Agente de reportes y trazabilidad', sub: 'Generación de reportes y evidencia' },
  ], 330, 30, 380),

  // ---- 4 servidores MCP ----
  ...['Caudal', 'Nivel', 'Presión', 'Temperatura'].map((eq, i) => ({
    id: `mcp-${i}`, type: 'caja', position: { x: X0 + i * 262, y: 450 },
    data: { titulo: `Servidor MCP ${eq}`, tono: 'c4', w: 250,
      items: ['Consulta de datos actuales e históricos', 'Diagnóstico', 'Consulta de grafo de conocimiento', 'Grafo de conocimiento'] },
  })),
  { id: 'mcp-reg', type: 'caja', position: { x: 1300, y: 450 }, data: { titulo: 'Registro de equipos y metadatos', tono: 'c4', w: 240,
    sub: 'equipos.json (módulos, UNS, MCP, grafos, variables)' } },

  // ---- 3 UNS y persistencia ----
  ...fila(680, 'c3', [
    { id: 'mqtt', titulo: 'Broker MQTT Mosquitto' },
    { id: 'uns', titulo: 'UNS del laboratorio', items: ['uss/campus/lab-automatizacion/sl01la07/', 'caudal-mcc09/ · nivel-mcn09/', 'presion-mcp09/ · temperatura-mct09/'] },
    { id: 'ing', titulo: 'Ingestores MQTT', items: ['Ingestor caudal', 'Ingestor nivel', 'Ingestor presión', 'Ingestor temperatura'] },
    { id: 'pg', titulo: 'PostgreSQL 16 + TimescaleDB 2.17.2', items: ['Datos en vivo', 'Históricos SCADA/LVM', 'Rol mcp_lector (solo lectura)', 'Series de tiempo industrial'] },
    { id: 'imp', titulo: 'Importador de históricos SCADA/LVM', sub: 'Datos históricos' },
  ]),

  // ---- 2 edge ----
  ...fila(890, 'c2', [
    { id: 'e-s7', titulo: 'conector_edge_s7200.py', sub: 'S7 mediante CP243-1 (Siemens S7-200)' },
    { id: 'e-ml', titulo: 'conector_edge_ml1100.py', sub: 'EtherNet/IP – PCCC (Allen-Bradley MicroLogix 1100)' },
    { id: 'e-cfp', titulo: 'conector_edge_cfp2200.py', sub: 'NI-PSP mediante DataSocket (NI Compact FieldPoint)' },
    { id: 'e-tw', titulo: 'conector_edge_twido.py', sub: 'Modbus TCP (Schneider Twido)' },
  ]),

  // ---- 1 fuentes ----
  ...fila(1050, 'c1', [
    { id: 'f-cau', titulo: 'Caudal MCC-09', sub: 'Siemens S7-200' },
    { id: 'f-niv', titulo: 'Nivel MCN-09', sub: 'Allen-Bradley MicroLogix 1100' },
    { id: 'f-pre', titulo: 'Presión MCP-09', sub: 'NI Compact FieldPoint' },
    { id: 'f-tem', titulo: 'Temperatura MCT-09', sub: 'Schneider Twido' },
    { id: 'f-his', titulo: 'Históricos SCADA/LVM', sub: 'Datos históricos' },
  ]),

  // ---- columna derecha ----
  { id: 'mon', type: 'caja', position: { x: ANCHO + 40, y: 0 }, data: { titulo: 'Monitoreo y evaluación', tono: 'mon', w: 280, items: [
    'Grafana (4 dashboards): caudal, nivel, presión, temperatura, tendencias',
    'Logs: conectores, ingestores, ejecución MCP',
    'Pruebas unitarias: planificador, permisos',
    'Casos de evaluación: consultas reproducibles, resultados esperados',
    'Evidencia: herramientas utilizadas, agente responsable, fuentes consultadas, marcas de tiempo',
  ] } },
  { id: 'seg', type: 'caja', position: { x: ANCHO + 40, y: 700 }, data: { titulo: 'Seguridad y límites', tono: 'seg', w: 280, items: [
    'Arquitectura de solo lectura: sin escritura hacia PLC',
    'MCP aislado con rol de base de datos lector',
    'Listas blancas de herramientas por agente',
    'Coordinador sin herramientas directas',
    'Trazabilidad de llamadas',
    'Separación entre evidencia y conclusiones del LLM',
  ] } },
];

const flecha = { type: MarkerType.ArrowClosed, width: 16, height: 16 };
const e = (id: string, source: string, target: string, label?: string, extra: Partial<Edge> = {}): Edge => ({
  id, source, target, label, markerEnd: flecha, className: 'al-edge', labelBgPadding: [6, 3], labelBgBorderRadius: 4, ...extra,
});

const edges: Edge[] = [
  e('6-5', 'ui-chat', 'coord', 'Lenguaje natural / API REST · WebSocket · SSE', { markerStart: flecha }),
  e('c-llm', 'coord', 'llm', undefined, { sourceHandle: 'der', targetHandle: 'izq', markerStart: flecha, animated: true }),
  e('c-a1', 'coord', 'ag-consulta'), e('c-a2', 'coord', 'ag-diag'), e('c-a3', 'coord', 'ag-rep'),
  ...[0, 1, 2, 3].map((i) => e(`a-m${i}`, 'ag-consulta', `mcp-${i}`, i === 0 ? 'MCP (JSON-RPC 2.0 sobre stdio)' : undefined)),
  ...[0, 1, 2, 3].map((i) => e(`d-m${i}`, 'ag-diag', `mcp-${i}`)),
  e('r-reg', 'ag-rep', 'mcp-reg'),
  ...[0, 1, 2, 3].map((i) => e(`m-pg${i}`, `mcp-${i}`, 'pg', i === 2 ? 'SQL de solo lectura (TimescaleDB)' : undefined)),
  e('mq-uns', 'mqtt', 'uns', undefined, { sourceHandle: 'der', targetHandle: 'izq' }),
  e('uns-ing', 'uns', 'ing', undefined, { sourceHandle: 'der', targetHandle: 'izq' }),
  e('ing-pg', 'ing', 'pg', undefined, { sourceHandle: 'der', targetHandle: 'izq' }),
  e('imp-pg', 'imp', 'pg', undefined, { sourceHandle: 'arr', targetHandle: 'aba' }),
  ...['e-s7', 'e-ml', 'e-cfp', 'e-tw'].map((c, i) => e(`edge-mq${i}`, c, 'mqtt', i === 0 ? 'MQTT — publicación en el UNS' : undefined, { animated: true, sourceHandle: 'arr', targetHandle: 'aba' })),
  e('f1', 'f-cau', 'e-s7', 'S7', { animated: true, sourceHandle: 'arr', targetHandle: 'aba' }),
  e('f2', 'f-niv', 'e-ml', 'EtherNet/IP – PCCC', { animated: true, sourceHandle: 'arr', targetHandle: 'aba' }),
  e('f3', 'f-pre', 'e-cfp', 'NI-PSP / DataSocket', { animated: true, sourceHandle: 'arr', targetHandle: 'aba' }),
  e('f4', 'f-tem', 'e-tw', 'Modbus TCP', { animated: true, sourceHandle: 'arr', targetHandle: 'aba' }),
  e('f5', 'f-his', 'imp', 'archivos LVM', { sourceHandle: 'arr', targetHandle: 'aba' }),
];

export function ArquitecturaLogicaPage() {
  return (
    <section className="panel al-panel">
      <div className="panel-head">
        <div>
          <h2>Arquitectura multiagente MCP-UNS implementada</h2>
          <span className="panel-sub">Integración y análisis de datos industriales · arrastra para moverte, rueda para zoom</span>
        </div>
      </div>
      <div className="al-wrap">
        <ReactFlowProvider>
          <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.04 }}
            nodesConnectable={false} elementsSelectable={false} proOptions={{ hideAttribution: true }} minZoom={0.2} maxZoom={2}>
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
      <p className="panel-sub" style={{ marginTop: 10 }}>
        <b>Alcance del prototipo:</b> integración de cuatro módulos industriales del laboratorio, operación de solo lectura y
        orquestación multiagente mediante herramientas MCP.
      </p>
    </section>
  );
}
