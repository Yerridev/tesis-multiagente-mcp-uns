import { useEffect, useMemo, useRef, type CSSProperties, type ReactNode } from 'react';
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, ReactFlowProvider, getSmoothStepPath, getStraightPath, useEdges, useNodeId, useReactFlow, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import { WaterSupplyNode } from './WaterSupplyNode';
import { CatalogEndNode, CatalogJunctionNode, CatalogPumpNode, CatalogValveNode } from './CatalogParts';

/* ============================================================
   Diagrama mímico de TEMPERATURA — puerto de BOSETOS/scada-temp
   100 % solo lectura: ningún nodo emite órdenes al equipo.
   ============================================================ */

type Data = Record<string, unknown>;

export interface TempSenal {
  online: boolean;
  tempControl: number | null;   // T2 principal, °C
  tempCooler: number | null;    // T1 enfriamiento, °C
  nivel1Pct: number | null;
  nivel2Pct: number | null;
  bomba: boolean | null;
  caudal: number | null;        // L/min
  heaterPct: number | null;     // resistencia 0-100 %
  coolerOn: boolean | null;     // enfriador
  valvulas: Record<string, boolean | null>;
  altoTE: boolean | null;
  bajoTE: boolean | null;
  altoTP: boolean | null;
  bajoTP: boolean | null;
}

function Port({ id, position, style }: { id: string; position: Position; style?: CSSProperties }) {
  return (
    <>
      <Handle id={id} type="source" position={position} style={style} isConnectable={false} />
      <Handle id={id} type="target" position={position} style={style} isConnectable={false} />
    </>
  );
}

const Sw = ({ on }: { on: boolean | null }) => <i className={on ? 'led led--on' : 'led'} />;

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
    <div className="valve nodrag nopan" title="Solo lectura · sin órdenes al equipo" style={{ width: vertical ? 40 : 70, height: vertical ? 70 : 40 }}>
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

/* ───────────── Bomba con variador ───────────── */
function PumpNode({ data }: NodeProps) {
  const d = data as Data;
  const on = d.on === true;
  const known = d.on !== null && d.on !== undefined;
  return (
    <div className="pump nodrag nopan" title="Solo lectura · sin órdenes al equipo" style={{ width: 220, height: 100 }}>
      <div className="pump__hit">
        <svg width="220" height="100" viewBox="0 0 220 100" aria-hidden>
          <defs>
            <linearGradient id="tp-g-motor" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#3b6bff" />
              <stop offset="1" stopColor="#1b2fa8" />
            </linearGradient>
            <linearGradient id="tp-g-casing" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#f4f6f8" />
              <stop offset="1" stopColor="#aab4be" />
            </linearGradient>
          </defs>
          <rect x="165" y="0" width="10" height="20" className="v-pipe" />
          <rect x="194" y="45" width="26" height="10" className="v-pipe" />
          <rect x="0" y="22" width="102" height="56" rx="8" fill="url(#tp-g-motor)" />
          {[14, 26, 38, 50, 62, 74, 86].map((x) => (
            <line key={x} x1={x} y1="26" x2={x} y2="74" stroke="#0e1a66" strokeWidth="2" opacity=".55" />
          ))}
          <rect x="102" y="32" width="14" height="36" fill="#7b8794" />
          <rect x="116" y="18" width="80" height="64" rx="12" fill="url(#tp-g-casing)" />
          <g className={on ? 'impeller impeller--on' : 'impeller'}>
            <circle cx="156" cy="50" r="19" fill="#d5dce3" stroke="#8795a3" strokeWidth="2" />
            {[0, 60, 120, 180, 240, 300].map((a) => (
              <line key={a} x1="156" y1="50" x2="156" y2="34" stroke="#5b6b7d" strokeWidth="3" strokeLinecap="round" transform={`rotate(${a} 156 50)`} />
            ))}
          </g>
          <circle cx="12" cy="12" r="5" className={on && known ? 'led led--on' : 'led'} />
        </svg>
      </div>
      <span className="tag" style={{ left: 110, top: -24 }}>BOMBA · {!known ? 'SIN DATO' : on ? 'MARCHA' : 'PARO'}</span>
      <Port id="discharge" position={Position.Top} style={{ left: 170 }} />
      <Port id="suction" position={Position.Right} />
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

/* T1 · tanque de enfriamiento (con serpentín) */
function TankT1Node({ data }: NodeProps) {
  const d = data as Data;
  const pct = typeof d.nivelPct === 'number' ? d.nivelPct : null;
  const temp = typeof d.temp === 'number' ? d.temp : null;
  const coil = d.coolant === true;
  return (
    <div className="tank" style={{ width: 210, height: 245 }}>
      <SteelTank w={210} h={245} fill={pct} id="tpt1">
        <path d="M24 120 H186 V140 H24 V160 H186 V180 H24 V188 H186" fill="none" className={coil ? 'coil coil--cold' : 'coil'} />
        <rect x="-10" y="52" width="14" height="16" rx="3" className={d.altoTE === true ? 'level-switch-orange on' : 'level-switch-orange'} />
        <rect x="-10" y="182" width="14" height="16" rx="3" className={d.bajoTE === true ? 'level-switch-orange on' : 'level-switch-orange'} />
      </SteelTank>
      <div className="tank__readout"><strong>{temp == null ? '—' : temp.toFixed(0)}</strong><span>{temp == null ? 'sin dato' : '°C'}</span></div>
      <span className="tag" style={{ left: 8, top: 8 }}>T1 · ENFRIAMIENTO · {pct == null ? 'SIN DATO' : `${pct.toFixed(0)} %`}</span>
      <span className="tag level-tag" style={{ right: 224, top: 60 }}>NIVEL ALTO <Sw on={d.altoTE === true} /></span>
      <span className="tag level-tag" style={{ right: 224, top: 190 }}>NIVEL BAJO <Sw on={d.bajoTE === true} /></span>
      <Port id="in" position={Position.Bottom} style={{ left: 30 }} />
      <Port id="ovf" position={Position.Bottom} style={{ left: 130 }} />
      <Port id="retV2" position={Position.Bottom} style={{ left: 175 }} />
      <Port id="v1" position={Position.Top} style={{ left: 150 }} />
      <Port id="coilU" position={Position.Right} style={{ top: 120 }} />
      <Port id="coilD" position={Position.Right} style={{ top: 188 }} />
    </div>
  );
}

/* Sensor de temperatura — mismo diseño que BOSETOS/scada-sensor4 (vertical, cabeza a la izquierda) */
const SENSOR_ROT: Record<string, number> = { up: 0, right: 90, down: 180, left: 270 };

function TempSensorNode({ data }: NodeProps) {
  const d = data as Data;
  const label = String(d.label ?? 'TEMPERATURA SALIDA');
  const dir = String(d.dir ?? 'left');
  const known = typeof d.temp === 'number';
  const t = known ? (d.temp as number) : 0;
  const col = known ? `hsl(${210 - Math.min(100, Math.max(0, t)) * 2.1} 85% 58%)` : '#5a6b7c';
  const rot = SENSOR_ROT[dir] ?? 270;
  const vertical = dir === 'left' || dir === 'right';
  const headY = vertical ? -52 : -44; // en vertical la cabeza es más larga: al girar, la pantalla queda más ancha
  const sy = vertical ? -48 : -40;
  const sh = vertical ? 28 : 20;
  const sc = sy + sh / 2;
  const hue = 210 - Math.min(100, Math.max(0, t)) * 2.1;
  const disp = known ? `hsl(${hue} 90% 70%)` : '#5a6b7c';
  const shown = known ? `${Math.round(t)}°` : '--';
  const em = Math.min(10, 25 / (0.6 * shown.length));
  const tag: CSSProperties =
    dir === 'up' ? { left: -22, top: -70, width: 114, textAlign: 'center' }
      : dir === 'down' ? { left: -22, top: 92, width: 114, textAlign: 'center' }
        : dir === 'right' ? { left: 100, top: 25 } : { right: 100, top: 25 };
  return (
    <div className="valve nodrag nopan" title="Solo lectura · sin órdenes al equipo" style={{ width: vertical ? 40 : 70, height: vertical ? 70 : 40 }}>
      <div style={{ position: 'absolute', left: vertical ? -15 : 0, top: vertical ? 15 : 0, width: 70, height: 40, transform: `rotate(${rot}deg)` }}>
        <svg width="70" height="40" viewBox="0 0 70 40" overflow="visible" role="img" aria-label={`${label}: ${known ? `${t.toFixed(1)} grados Celsius` : 'sin dato'}`}>
          <rect x="0" y="15" width="70" height="10" className="v-pipe" />
          <rect x="24" y="11" width="22" height="18" rx="3" className="v-flange" />
          <rect x="31" y="-6" width="8" height="18" className="ts-stem" />
          <rect x="28" y="3" width="14" height="5" rx="1" className="ts-nut" />
          <circle cx="35" cy="20" r="3.5" fill={col} stroke="#0b141c" strokeWidth="1" style={{ transition: 'fill .4s' }} />
          <rect x="17" y={headY} width="36" height={-5 - headY} rx="5" className="ts-head" />
          <rect x="21" y={sy} width="28" height={sh} rx="2" className="ts-screen" />
          <text x="35" y={sc} textAnchor="middle" dominantBaseline="central" transform={`rotate(${-rot} 35 ${sc})`} className="ts-text" style={{ fill: disp, fontSize: em }}>
            {shown}
          </text>
          <circle cx="35" cy="-11" r="2.5" className="ts-led" />
        </svg>
      </div>
      <span className="tag" style={tag}>{label}</span>
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

/* T2 · tanque principal (con resistencia) */
function TankT2Node({ data }: NodeProps) {
  const d = data as Data;
  const pct = typeof d.nivelPct === 'number' ? d.nivelPct : null;
  const temp = typeof d.temp === 'number' ? d.temp : null;
  const heater = typeof d.heaterPct === 'number' ? d.heaterPct : null;
  const heating = heater != null && heater > 0;
  return (
    <div className="tank" style={{ width: 215, height: 220 }}>
      <SteelTank w={215} h={220} fill={pct} id="tpt2">
        <path d="M30 195 l12 -16 l12 32 l12 -32 l12 32 l12 -32 l12 32 l12 -32 l12 32 l12 -16" fill="none" className={heating ? 'heater heater--on' : 'heater'} />
        <rect x="206" y="42" width="14" height="16" rx="3" className={d.altoTP === true ? 'level-switch-orange on' : 'level-switch-orange'} />
        <rect x="206" y="167" width="14" height="16" rx="3" className={d.bajoTP === true ? 'level-switch-orange on' : 'level-switch-orange'} />
      </SteelTank>
      <div className="tank__readout"><strong>{temp == null ? '—' : temp.toFixed(0)}</strong><span>{temp == null ? 'sin dato' : '°C'}</span></div>
      <span className="tag" style={{ left: 8, top: 8 }}>T2 · PRINCIPAL · {pct == null ? 'SIN DATO' : `${pct.toFixed(0)} %`}</span>
      <span className="tag level-tag level-tag--right" style={{ left: 224, top: 50 }}><Sw on={d.altoTP === true} /> NIVEL ALTO</span>
      <span className="tag level-tag level-tag--right" style={{ left: 224, top: 175 }}><Sw on={d.bajoTP === true} /> NIVEL BAJO</span>
      <span className="tag" style={{ left: 12, top: 168 }}>RESISTENCIA {heater == null ? 'SIN DATO' : `${heater} %`} <Sw on={heating} /></span>
      <Port id="inB" position={Position.Top} style={{ left: 30 }} />
      <Port id="inA" position={Position.Top} style={{ left: 75 }} />
      <Port id="inS" position={Position.Bottom} style={{ left: 175 }} />
      <Port id="out" position={Position.Bottom} style={{ left: 125 }} />
    </div>
  );
}

/* Enfriador (chiller) */
function ChillerNode({ data }: NodeProps) {
  const d = data as Data;
  const on = d.on === true;
  const known = d.on !== null && d.on !== undefined;
  return (
    <div className="nodrag nopan" title="Solo lectura · sin órdenes al equipo" style={{ width: 90, height: 70, position: 'relative' }}>
      <div className="pump__hit">
        <svg width="90" height="70" viewBox="0 0 90 70" aria-hidden>
          <rect x="2" y="8" width="86" height="54" rx="6" fill="#c9d3dd" stroke="#4a5560" strokeWidth="2" />
          {[14, 26, 38, 50, 62, 74].map((x) => <line key={x} x1={x} y1="12" x2={x} y2="58" stroke="#8a96a8" strokeWidth="2" />)}
          <g className={on ? 'impeller impeller--on' : 'impeller'} style={{ transformOrigin: '45px 35px' }}>
            <circle cx="45" cy="35" r="17" fill="#e8eef4" stroke="#4a5560" strokeWidth="2" />
            {[0, 90, 180, 270].map((a) => <path key={a} d="M45 35 q8 -12 0 -15 q-8 4 0 15" fill="#4cc3f2" transform={`rotate(${a} 45 35)`} />)}
          </g>
        </svg>
      </div>
      <span className="tag" style={{ left: 0, top: -24 }}>ENFRIADOR <Sw on={known ? on : null} /></span>
      <Port id="outU" position={Position.Left} style={{ top: 22 }} />
      <Port id="outD" position={Position.Left} style={{ top: 52 }} />
    </div>
  );
}

/* Caudal (L/min) */
function FlowReadoutNode({ data }: NodeProps) {
  const d = data as Data;
  const q = typeof d.q === 'number' ? d.q : null;
  return (
    <div className="readout">
      <span>CAUDAL (L/min)</span>
      <strong>{q == null ? '—' : q.toFixed(0)}</strong>
    </div>
  );
}

const nodeTypes = {
  junction: CatalogJunctionNode,
  end: CatalogEndNode,
  valve: CatalogValveNode,
  pump: CatalogPumpNode,
  tankT1: TankT1Node,
  tankT2: TankT2Node,
  chiller: ChillerNode,
  flow: FlowReadoutNode,
  supply: WaterSupplyNode,
  tempSensor: TempSensorNode,
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

/* ───────────── Geometría (idéntica a BOSETOS/scada-temp) ───────────── */
const fixed = { draggable: false, selectable: false };
const junction = (id: string, cx: number, cy: number): Node => ({ id, type: 'junction', position: { x: cx - 1, y: cy - 1 }, data: {}, ...fixed });
const valve = (valveId: string, cx: number, cy: number, orientation: 'h' | 'v', nominal: boolean, lever?: 'left'): Node => ({
  id: valveId, type: 'valve', ...fixed,
  position: orientation === 'h' ? { x: cx - 35, y: cy - 20 } : { x: cx - 20, y: cy - 35 },
  data: { valveId, label: valveId, orientation, nominal, ...(lever ? { lever } : {}) },
});
const end = (id: string, x: number, y: number): Node => ({ id, type: 'end', position: { x, y }, data: { side: 'l' }, ...fixed });

const BASE_NODES: Node[] = [
  { id: 'pump', type: 'pump', position: { x: 285, y: 970 }, data: {}, ...fixed },
  { id: 'flow', type: 'flow', position: { x: 330, y: 760 }, data: {}, ...fixed },
  { id: 't1', type: 'tankT1', position: { x: 425, y: 270 }, data: {}, ...fixed },
  { id: 't2', type: 'tankT2', position: { x: 525, y: 690 }, data: {}, ...fixed },
  { id: 'chiller', type: 'chiller', position: { x: 780, y: 430 }, data: {}, ...fixed },
  { id: 'TS', type: 'tempSensor', position: { x: 630, y: 925 }, data: { label: 'TEMPERATURA SALIDA', dir: 'left', src: 'control' }, ...fixed },
  { id: 'TSE', type: 'tempSensor', position: { x: 580, y: 565 }, data: { label: 'TEMPERATURA ENTRADA', dir: 'right', src: 'cooler' }, ...fixed },
  /* Posición nominal: V2 abierta · V1 y V3 cerradas */
  valve('V1', 670, 215, 'h', false), valve('V2', 555, 600, 'v', true, 'left'), valve('V3', 735, 985, 'h', false),
  junction('JV', 575, 215), junction('JS', 650, 1020),
  end('END1', 705, 203),
  { id: 'SUPPLY', type: 'supply', position: { x: 820, y: 927 }, data: { side: 'l' }, ...fixed },
];

const ed = (id: string, source: string, sh: string, target: string, th: string, type: 'pipe' | 'coolant' = 'pipe', extra: Data = {}): Edge => ({
  id, source, sourceHandle: sh, target, targetHandle: th, type, data: { active: false, ...extra },
});

const EDGES: Edge[] = [
  ed('d1', 'pump', 'discharge', 't1', 'in'),
  ed('r1', 't1', 'retV2', 'TSE', 't'), ed('r2', 'TSE', 'b', 't2', 'inA'),
  ed('ov', 't1', 'ovf', 'V2', 't'), ed('ov2', 'V2', 'b', 't2', 'inB'),
  ed('s1', 't2', 'out', 'TS', 't'), ed('s1b', 'TS', 'b', 'JS', 't'), ed('s2', 'JS', 'l', 'pump', 'suction'),
  ed('x1', 'SUPPLY', 'l', 'V3', 'r'), ed('x2', 'V3', 'l', 't2', 'inS'),
  ed('f1', 'END1', 'l', 'V1', 'r'), ed('f2', 'V1', 'l', 'JV', 'r'), ed('f3', 'JV', 'b', 't1', 'v1'),
  /* Refrigerante: la superior gira cerca del enfriador, la inferior antes (escalonado, sin cruces) */
  ed('c1', 'chiller', 'outU', 't1', 'coilU', 'coolant', { turnX: 745 }),
  ed('c2', 'chiller', 'outD', 't1', 'coilD', 'coolant', { turnX: 690 }),
];

/* ───────────── Tubería de refrigerante (enfriador ↔ serpentín del T1) ───────────── */
function CoolantEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  /* Recorrido ortogonal escalonado: sale horizontal del tanque, gira 90° en su propio
     punto (turnX) y sigue horizontal hasta el enfriador. Cada tubo tiene el suyo. */
  const turn = (data as Data | undefined)?.turnX;
  const turnX = typeof turn === 'number' ? turn : (sourceX + targetX) / 2;
  const path = `M ${targetX},${targetY} L ${turnX},${targetY} L ${turnX},${sourceY} L ${sourceX},${sourceY}`;
  return (
    <g>
      <path d={path} className="coolant-wall" />
      <path d={path} className="coolant-bore" />
    </g>
  );
}

const edgeTypes = { pipe: PipeEdge, coolant: CoolantEdge };

/* ───────────── Lienzo con re-encaje automático ───────────── */
function Flow({ senal }: { senal: TempSenal }) {
  const rf = useReactFlow();
  const ref = useRef<HTMLDivElement>(null);

  const nodes = useMemo<Node[]>(() => {
    const activo = senal.online && senal.bomba === true;
    return BASE_NODES.map((n) => {
      const data: Data = { ...n.data };
      if (n.type === 'pump') data.on = senal.bomba;
      if (n.type === 'tempSensor') data.temp = (n.data as Data).src === 'cooler' ? senal.tempCooler : senal.tempControl;
      if (n.type === 'flow') data.q = senal.caudal;
      if (n.type === 'tankT1') {
        data.nivelPct = senal.nivel1Pct;
        data.temp = senal.tempCooler;
        data.coolant = senal.online && senal.coolerOn === true;
        data.altoTE = senal.altoTE;
        data.bajoTE = senal.bajoTE;
      }
      if (n.type === 'tankT2') {
        data.nivelPct = senal.nivel2Pct;
        data.temp = senal.tempControl;
        data.heaterPct = senal.heaterPct;
        data.altoTP = senal.altoTP;
        data.bajoTP = senal.bajoTP;
      }
      if (n.type === 'chiller') data.on = senal.coolerOn;
      if (n.type === 'valve') {
        const nom = (n.data as Data).nominal;
        data.open = senal.valvulas[String(n.id)] ?? (typeof nom === 'boolean' ? nom : null);
      }
      if (n.type === 'supply') data.active = senal.online && senal.valvulas.V3 === true;
      if (n.type === 'end') data.active = activo;
      return { ...n, data };
    });
  }, [senal]);

  const edges = useMemo<Edge[]>(() => EDGES.map((e) => ({
    ...e,
    // se conserva el data original (p. ej. turnX de las tuberías de refrigerante) y solo se actualiza "active"
    data: { ...e.data, active: e.id === 'x1' || e.id === 'x2' ? senal.online && senal.valvulas.V3 === true : senal.online && senal.bomba === true },
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

export function TempFlow({ senal }: { senal: TempSenal }) {
  return (
    <ReactFlowProvider>
      <Flow senal={senal} />
    </ReactFlowProvider>
  );
}
