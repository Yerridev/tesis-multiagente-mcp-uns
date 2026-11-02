import { useEffect, useMemo, useRef, type CSSProperties, type ReactNode } from 'react';
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, ReactFlowProvider, getStraightPath, useEdges, useNodeId, useReactFlow, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import { WaterSupplyNode } from './WaterSupplyNode';
import { CatalogEndNode, CatalogJunctionNode, CatalogPumpNode, CatalogValveNode } from './CatalogParts';

/* ============================================================
   Diagrama mímico de PRESIÓN (MCP-09) — puerto de BOSETOS/scada-pressure
   100 % solo lectura: ningún nodo emite órdenes al controlador.
   ============================================================ */

type Data = Record<string, unknown>;

export interface PresionSenal {
  online: boolean;
  presion: number | null;     // transmisor de presión del T2, PSI
  nivelPct: number | null;    // nivel del tanque T1, 0-100 %
  bomba: boolean | null;
  valvulaPct: number | null;  // válvula proporcional %
  valvulas: Record<string, boolean | null>;
  nivelAlto: boolean | null;
  nivelBajo: boolean | null;
}

function Port({ id, position, style }: { id: string; position: Position; style?: CSSProperties }) {
  return (
    <>
      <Handle id={id} type="source" position={position} style={style} isConnectable={false} />
      <Handle id={id} type="target" position={position} style={style} isConnectable={false} />
    </>
  );
}

/* ───────────── Unión de tuberías ───────────── */
const FIT_ARM: Record<string, { body: [number, number, number, number]; flange: [number, number, number, number] }> = {
  l: { body: [2, 17, 20, 10], flange: [0, 13, 5, 18] }, r: { body: [22, 17, 20, 10], flange: [39, 13, 5, 18] },
  t: { body: [17, 2, 10, 20], flange: [13, 0, 18, 5] }, b: { body: [17, 22, 10, 20], flange: [13, 39, 18, 5] },
};
function JunctionNode() {
  const id = useNodeId();
  const edges = useEdges();
  const arms = [...new Set(edges.filter((e) => e.source === id || e.target === id).map((e) => e.source === id ? e.sourceHandle : e.targetHandle).filter((h): h is string => !!h))];
  return (
    <div className="junction">
      {arms.length >= 2 && <svg width="44" height="44" viewBox="0 0 44 44" className="ca-fitting" aria-hidden>
        {['ca-fit-outline', 'ca-fit-body'].map((cls) => <g className={cls} key={cls}><rect x="17" y="17" width="10" height="10" rx="3" />{arms.map((a) => FIT_ARM[a] && <g key={a}><rect x={FIT_ARM[a].body[0]} y={FIT_ARM[a].body[1]} width={FIT_ARM[a].body[2]} height={FIT_ARM[a].body[3]} /><rect x={FIT_ARM[a].flange[0]} y={FIT_ARM[a].flange[1]} width={FIT_ARM[a].flange[2]} height={FIT_ARM[a].flange[3]} rx="1.5" /></g>)}</g>)}
      </svg>}
      <Port id="t" position={Position.Top} />
      <Port id="b" position={Position.Bottom} />
      <Port id="l" position={Position.Left} />
      <Port id="r" position={Position.Right} />
    </div>
  );
}

/* ───────────── Extremo abierto de tubería ───────────── */
function EndNode({ data }: NodeProps) {
  const d = data as Data;
  const side = String(d.side) as 'l' | 'r' | 't';
  return (
    <div className={`pipe-end pipe-end--${side}`}>
      <div className="pipe-end__flange" />
      {d.active === true && <span className="drip" />}
      <Port id={side} position={side === 'l' ? Position.Left : side === 't' ? Position.Top : Position.Right} />
    </div>
  );
}

/* ───────────── Válvula de bola (solo lectura) ───────────── */
function ValveGlyph({ open }: { open: boolean | null }) {
  const cls = open === true ? 'v-body v-body--open' : open === false ? 'v-body v-body--closed' : 'v-body v-body--unknown';
  return (
    <svg width="70" height="40" viewBox="0 0 70 40" overflow="visible" aria-hidden>
      <rect x="0" y="15" width="70" height="10" className="v-pipe" />
      <rect x="22" y="12" width="26" height="16" rx="3" className="v-flange" />
      <circle cx="35" cy="20" r="10" className={cls} />
      {open === null && <text x="35" y="24" textAnchor="middle" className="v-q">?</text>}
      <line x1="35" y1="10" x2="35" y2="6" className="v-stem" />
      <rect
        x="33" y="3" width="30" height="5" rx="2.5" className="v-lever"
        style={{ transformOrigin: '35px 5.5px', transform: `rotate(${open === null ? -45 : open ? 0 : -90}deg)` }}
      />
    </svg>
  );
}

function ValveNode({ data }: NodeProps) {
  const d = data as Data;
  const orientation = String(d.orientation) as 'h' | 'v';
  const open = (d.open as boolean | null) ?? null;
  const vertical = orientation === 'v';
  return (
    <div className="valve nodrag nopan" title="Solo lectura · sin órdenes al controlador" style={{ width: vertical ? 40 : 70, height: vertical ? 70 : 40 }}>
      <div className="valve__hit" style={vertical ? { left: -15, top: 15, width: 70, height: 40, transform: 'rotate(90deg)' } : { left: 0, top: 0, width: 70, height: 40 }}>
        <ValveGlyph open={open} />
      </div>
      <span className="valve__tag" style={vertical ? { left: 46, top: 26 } : { left: 0, top: -18, width: 70 }}>
        {String(d.label ?? '')}
      </span>
      {vertical ? (
        <>
          <Port id="t" position={Position.Top} />
          <Port id="b" position={Position.Bottom} />
        </>
      ) : (
        <>
          <Port id="l" position={Position.Left} />
          <Port id="r" position={Position.Right} />
        </>
      )}
    </div>
  );
}

/* ───────────── Válvula proporcional con actuador ───────────── */
function ProportionalValveNode({ data }: NodeProps) {
  const d = data as Data;
  const pct = typeof d.pct === 'number' ? d.pct : null;
  return (
    <div className="valve" title="Solo lectura · sin órdenes al controlador" style={{ width: 70, height: 40 }}>
      <svg width="70" height="40" viewBox="0 0 70 40" overflow="visible" aria-hidden>
        <rect x="0" y="15" width="70" height="10" className="v-pipe" />
        <rect x="22" y="12" width="26" height="16" rx="3" className="v-flange" />
        <circle cx="35" cy="20" r="10" className={pct == null ? 'v-body v-body--unknown' : pct > 0 ? 'v-body v-body--open' : 'v-body v-body--closed'} />
        <line x1="35" y1="10" x2="35" y2="-4" className="v-stem" />
        <rect x="10" y="-30" width="50" height="26" rx="4" className="v-actuator" />
        <rect x="14" y="-12" width="42" height="4" rx="2" fill="#0003" />
        {pct != null && <rect x="14" y="-12" width={(42 * pct) / 100} height="4" rx="2" fill="#fff" />}
      </svg>
      <span className="tag" style={{ left: -45, top: -58, width: 170, textAlign: 'center' }}>
        VÁLVULA PROPORCIONAL · {pct == null ? 'SIN DATO' : `${pct} %`}
      </span>
      <Port id="l" position={Position.Left} />
      <Port id="r" position={Position.Right} />
    </div>
  );
}

/* ───────────── Bomba con motor (orientada hacia la izquierda) ───────────── */
function PumpNode({ data }: NodeProps) {
  const d = data as Data;
  const on = d.on === true;
  const known = d.on !== null && d.on !== undefined;
  return (
    <div className="pump nodrag nopan" title="Solo lectura · sin órdenes al controlador" style={{ width: 220, height: 100 }}>
      <div className="pump__hit">
        <svg width="220" height="100" viewBox="0 0 220 100" aria-hidden style={{ transform: 'scaleX(-1)' }}>
          <defs>
            <linearGradient id="pr-g-motor" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#3b6bff" />
              <stop offset="1" stopColor="#1b2fa8" />
            </linearGradient>
            <linearGradient id="pr-g-casing" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#f4f6f8" />
              <stop offset="1" stopColor="#aab4be" />
            </linearGradient>
          </defs>
          <rect x="165" y="0" width="10" height="20" className="v-pipe" />
          <rect x="194" y="45" width="26" height="10" className="v-pipe" />
          <rect x="0" y="22" width="102" height="56" rx="8" fill="url(#pr-g-motor)" />
          {[14, 26, 38, 50, 62, 74, 86].map((x) => (
            <line key={x} x1={x} y1="26" x2={x} y2="74" stroke="#0e1a66" strokeWidth="2" opacity=".55" />
          ))}
          <rect x="102" y="32" width="14" height="36" fill="#7b8794" />
          <rect x="116" y="18" width="80" height="64" rx="12" fill="url(#pr-g-casing)" />
          <g className={on ? 'impeller impeller--on' : 'impeller'}>
            <circle cx="156" cy="50" r="19" fill="#d5dce3" stroke="#8795a3" strokeWidth="2" />
            {[0, 60, 120, 180, 240, 300].map((a) => (
              <line key={a} x1="156" y1="50" x2="156" y2="34" stroke="#5b6b7d" strokeWidth="3" strokeLinecap="round" transform={`rotate(${a} 156 50)`} />
            ))}
          </g>
          <circle cx="12" cy="12" r="5" className={on && known ? 'led led--on' : 'led'} />
        </svg>
      </div>
      <span className="tag" style={{ left: 20, top: -24 }}>
        BOMBA · {!known ? 'SIN DATO' : on ? 'MARCHA' : 'PARO'}
      </span>
      <Port id="discharge" position={Position.Top} style={{ left: 50 }} />
      <Port id="suction" position={Position.Left} />
    </div>
  );
}

/* ───────────── Tanques de acero ───────────── */
function SteelTank({ w, h, fill, id, children }: { w: number; h: number; fill: number | null; id: string; children?: ReactNode }) {
  const y = fill == null ? h : h - (Math.min(100, Math.max(0, fill)) / 100) * h;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} overflow="visible" aria-hidden>
      <defs>
        <clipPath id={`${id}-clip`}><rect width={w} height={h} rx="16" /></clipPath>
        <linearGradient id={`${id}-steel`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#59606a" /><stop offset=".25" stopColor="#b9c0c8" />
          <stop offset=".45" stopColor="#eef1f4" /><stop offset=".75" stopColor="#8f98a2" /><stop offset="1" stopColor="#4f565f" />
        </linearGradient>
        <linearGradient id={`${id}-water`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#4cc3f2" stopOpacity=".95" /><stop offset="1" stopColor="#136ea3" stopOpacity=".95" />
        </linearGradient>
      </defs>
      <rect width={w} height={h} rx="16" fill={`url(#${id}-steel)`} />
      <g clipPath={`url(#${id}-clip)`} opacity=".72">
        <g style={{ transform: `translateY(${y}px)`, transition: 'transform .5s ease-out' }}>
          <path className="tank__wave" fill={`url(#${id}-water)`} d="M0 0 q28 -7 56 0 t56 0 t56 0 t56 0 t56 0 t56 0 t56 0 t56 0 V400 H0 Z" />
        </g>
      </g>
      <rect width={w} height={h} rx="16" fill="none" stroke="#2a323b" strokeWidth="2" />
      {children}
    </svg>
  );
}

function TankT1Node({ data }: NodeProps) {
  const d = data as Data;
  const pct = typeof d.nivelPct === 'number' ? d.nivelPct : null;
  const alto = d.alto === true;
  const bajo = d.bajo === true;
  return (
    <div className="tank" style={{ width: 190, height: 305 }}>
      <SteelTank w={190} h={305} fill={pct} id="prt1">
        <rect x="-10" y="34" width="14" height="16" rx="3" className={alto ? 'level-switch-orange on' : 'level-switch-orange'} />
        <rect x="-10" y="252" width="14" height="16" rx="3" className={bajo ? 'level-switch-orange on' : 'level-switch-orange'} />
      </SteelTank>
      <div className="tank__readout"><strong>{pct == null ? '—' : pct.toFixed(0)}</strong><span>{pct == null ? 'sin dato' : '%'}</span></div>
      <span className="tag level-tag" style={{ right: 204, top: 42 }}>NIVEL ALTO <i className={alto ? 'led led--alarm' : 'led'} /></span>
      <span className="tag level-tag" style={{ right: 204, top: 260 }}>NIVEL BAJO <i className={bajo ? 'led led--on' : 'led'} /></span>
      <span className="tag" style={{ left: 60, top: 10 }}>TANQUE T1</span>
      <Port id="in" position={Position.Top} style={{ left: 81 }} />
      <Port id="inR" position={Position.Top} style={{ left: 150 }} />
      <Port id="out" position={Position.Bottom} style={{ left: 98 }} />
    </div>
  );
}

function TankT2Node({ data }: NodeProps) {
  const d = data as Data;
  const psi = typeof d.psi === 'number' ? d.psi : null;
  const trip = psi != null && psi >= 55;
  return (
    <div className="tank" style={{ width: 130, height: 350 }}>
      <SteelTank w={130} h={350} fill={psi == null ? null : Math.min(90, 30 + psi * 0.8)} id="prt2">
        <rect x="50" y="-26" width="26" height="26" rx="3" fill="#2b323b" stroke="#8a96a8" />
        <rect x="92" y="-26" width="30" height="26" rx="3" fill="#232b34" stroke="#8a96a8" />
        <circle cx="107" cy="-13" r="8" fill={trip ? '#ff5d5d' : '#a02323'} />
      </SteelTank>
      <div className="psi"><span>Presión (PSI)</span><strong>{psi == null ? '—' : psi.toFixed(0)}</strong></div>
      <span className="tag" style={{ left: 36, top: 150 }}>TANQUE T2</span>
      <span className="tag" style={{ left: 2, top: -66, textAlign: 'center' }}>TRANSMISOR<br />DE PRESIÓN</span>
      <span className="tag" style={{ left: 128, top: -22 }}>PRESOSTATO</span>
      <Port id="inR" position={Position.Right} style={{ top: 320 }} />
      <Port id="air1" position={Position.Right} style={{ top: 225 }} />
      <Port id="air2" position={Position.Right} style={{ top: 241 }} />
      <Port id="outL" position={Position.Left} style={{ top: 320 }} />
    </div>
  );
}

function ChargerNode() {
  return (
    <div style={{ width: 50, height: 75, position: 'relative' }}>
      <svg width="50" height="75" viewBox="0 0 50 75" overflow="visible" aria-hidden>
        <path d="M5 20 q0 -16 20 -16 q20 0 20 16 V62 q0 10 -20 10 q-20 0 -20 -10 Z" fill="#c7ced6" stroke="#4a5560" strokeWidth="2" />
        <rect x="5" y="30" width="40" height="5" fill="#8a96a8" />
        {/* Dos tubos de latón en el costado izquierdo: el cargador se une al tanque con piezas metálicas, no con una tee */}
        <path d="M8 25 H-10" className="brass-pipe" />
        <path d="M8 41 H-10" className="brass-pipe" />
      </svg>
      <span className="tag" style={{ left: 58, top: 26 }}>CARGADOR DE AIRE</span>
      <Port id="b" position={Position.Bottom} style={{ left: 31 }} />
      <Port id="o1" position={Position.Left} style={{ top: 25 }} />
      <Port id="o2" position={Position.Left} style={{ top: 41 }} />
    </div>
  );
}

const nodeTypes = {
  junction: CatalogJunctionNode,
  end: CatalogEndNode,
  valve: CatalogValveNode,
  propValve: ProportionalValveNode,
  pump: CatalogPumpNode,
  tankT1: TankT1Node,
  tankT2: TankT2Node,
  charger: ChargerNode,
  supply: WaterSupplyNode,
};

/* ───────────── Tubería (borde ReactFlow) ───────────── */
function PipeEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  const [path] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  const flowing = (data as Data | undefined)?.active === true;
  return (
    <g>
      <path d={path} className="pipe-wall" />
      <path d={path} className="pipe-bore" />
      {flowing && (
        <>
          <path d={path} className="pipe-water" />
          <path d={path} className="pipe-flow" />
        </>
      )}
    </g>
  );
}

/* ───────────── Cable de aire: el cargador se une a la bomba con un cable amarillo ───────────── */
function HoseEdge({ sourceX, sourceY, targetX, targetY }: EdgeProps) {
  /* Ruta ortogonal: sube recto, gira por debajo del cargador y entra por su base.
     Evita cruzarse con las tuberías verticales de V4/V5/V6 y la línea de JE. */
  const yTurn = targetY + 28;
  const path = `M ${sourceX},${sourceY} L ${sourceX},${yTurn} L ${targetX},${yTurn} L ${targetX},${targetY}`;
  return (
    <g>
      <path d={path} className="air-cable" />
      <path d={path} className="air-cable-core" />
    </g>
  );
}

/* ───────────── Geometría (idéntica a BOSETOS/scada-pressure) ───────────── */
const fixed = { draggable: false, selectable: false };
const junction = (id: string, cx: number, cy: number): Node => ({ id, type: 'junction', position: { x: cx - 1, y: cy - 1 }, data: {}, ...fixed });
const valve = (valveId: string, cx: number, cy: number, orientation: 'h' | 'v', nominal: boolean): Node => ({
  id: valveId, type: 'valve', ...fixed,
  position: orientation === 'h' ? { x: cx - 35, y: cy - 20 } : { x: cx - 20, y: cy - 35 },
  data: { valveId, label: valveId, orientation, nominal },
});
const end = (id: string, x: number, y: number, side: 'r' | 't'): Node => ({ id, type: 'end', position: { x, y }, data: { side }, ...fixed });

const BASE_NODES: Node[] = [
  { id: 'pump', type: 'pump', position: { x: 785, y: 1338 }, data: { mirror: true, air: true }, ...fixed },
  { id: 't1', type: 'tankT1', position: { x: 307, y: 1020 }, data: {}, ...fixed },
  { id: 't2', type: 'tankT2', position: { x: 622, y: 840 }, data: {}, ...fixed },
  { id: 'ac', type: 'charger', position: { x: 760, y: 1040 }, data: {}, ...fixed },
  { id: 'PV', type: 'propValve', position: { x: 445, y: 715 }, data: {}, ...fixed },
  /* Posición nominal: V2, V5, V6 abiertas · V1, V3, V4, V7 cerradas */
  valve('V1', 300, 948, 'h', false), valve('V2', 388, 865, 'v', true), valve('V3', 300, 785, 'h', false), valve('V4', 770, 1213, 'h', false),
  valve('V5', 835, 1270, 'v', true), valve('V6', 760, 1330, 'h', true), valve('V7', 405, 1475, 'v', false),
  junction('JTL', 388, 735), junction('JV3', 388, 785), junction('JV1', 388, 948),
  junction('JLt2', 553, 985), junction('JLb2', 553, 1330), junction('JU', 585, 735), junction('JB', 585, 1160),
  junction('JR2', 457, 985),
  junction('JT', 405, 1388), junction('JD', 835, 1330), junction('J4', 835, 1213), junction('JE', 835, 1160),
  end('END1', 253, 936, 'r'), end('END3', 253, 773, 'r'), end('END4', 723, 1201, 'r'),
  { id: 'SUPPLY', type: 'supply', position: { x: 305, y: 1545 }, data: { side: 't' }, ...fixed },
];

const ed = (id: string, source: string, sh: string, target: string, th: string, type: 'pipe' | 'hose' = 'pipe'): Edge => ({
  id, source, sourceHandle: sh, target, targetHandle: th, type, data: { active: false },
});

const EDGES: Edge[] = [
  ed('o1', 't1', 'out', 'JT', 't'), ed('o2', 'JT', 'r', 'pump', 'suction'),
  ed('o3', 'V7', 't', 'JT', 'b'), ed('o4', 'SUPPLY', 't', 'V7', 'b'),
  ed('u1', 'pump', 'discharge', 'JD', 'b'),
  ed('l1', 'JD', 'l', 'V6', 'r'), ed('l2', 'V6', 'l', 'JLb2', 'r'), ed('l3', 'JLb2', 't', 'JLt2', 'b'),
  ed('l4', 'JLt2', 'l', 'JR2', 'r'), ed('l5', 'JR2', 'b', 't1', 'inR'),
  ed('t1', 'JD', 't', 'V5', 'b'), ed('t2', 'V5', 't', 'J4', 'b'), ed('t3', 'J4', 't', 'JE', 'b'),
  ed('t4', 'JE', 'l', 't2', 'inR'), ed('t6a', 'ac', 'o1', 't2', 'air1'), ed('t6b', 'ac', 'o2', 't2', 'air2'),
  ed('h1', 'pump', 'air', 'ac', 'b', 'hose'),
  ed('s1', 'J4', 'l', 'V4', 'r'), ed('s2', 'V4', 'l', 'END4', 'r'),
  ed('r1', 't2', 'outL', 'JB', 'r'), ed('r2', 'JB', 't', 'JU', 'b'), ed('r3', 'JU', 'l', 'PV', 'r'),
  ed('r4', 'PV', 'l', 'JTL', 'r'), ed('r5', 'JTL', 'b', 'JV3', 't'),
  ed('v1', 'JV3', 'l', 'V3', 'r'), ed('v2', 'V3', 'l', 'END3', 'r'),
  ed('v3', 'JV3', 'b', 'V2', 't'), ed('v4', 'V2', 'b', 'JV1', 't'),
  ed('f1', 'END1', 'r', 'V1', 'l'), ed('f2', 'V1', 'r', 'JV1', 'l'),
  ed('n1', 'JV1', 'b', 't1', 'in'),
];

const edgeTypes = { pipe: PipeEdge, hose: HoseEdge };

/* ───────────── Lienzo con re-encaje automático ───────────── */
function Flow({ senal }: { senal: PresionSenal }) {
  const rf = useReactFlow();
  const ref = useRef<HTMLDivElement>(null);

  const nodes = useMemo<Node[]>(() => {
    const activo = senal.online && senal.bomba === true;
    return BASE_NODES.map((n) => {
      const data: Data = { ...n.data };
      if (n.type === 'pump') data.on = senal.bomba;
      if (n.type === 'tankT1') { data.nivelPct = senal.nivelPct; data.alto = senal.nivelAlto; data.bajo = senal.nivelBajo; }
      if (n.type === 'tankT2') data.psi = senal.presion;
      if (n.type === 'propValve') data.pct = senal.valvulaPct;
      if (n.type === 'valve') {
        const nom = (n.data as Data).nominal;
        data.open = senal.valvulas[String(n.id)] ?? (typeof nom === 'boolean' ? nom : null);
      }
      if (n.type === 'supply') data.active = senal.online && senal.valvulas.V7 === true;
      if (n.type === 'end') data.active = activo;
      return { ...n, data };
    });
  }, [senal]);

  const edges = useMemo<Edge[]>(() => EDGES.map((e) => ({
    ...e,
    data: { active: e.id === 'o3' || e.id === 'o4' ? senal.online && senal.valvulas.V7 === true : senal.online && senal.bomba === true },
  })), [senal]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => rf.fitView({ padding: 0.2 }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [rf]);

  return (
    <div className="ca-canvas" ref={ref}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3} maxZoom={2} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}>
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.2} />
        <Controls showInteractive={false} position="top-right" fitViewOptions={{ padding: 0.2 }} />
      </ReactFlow>
    </div>
  );
}

export function PressureFlow({ senal }: { senal: PresionSenal }) {
  return (
    <ReactFlowProvider>
      <Flow senal={senal} />
    </ReactFlowProvider>
  );
}
