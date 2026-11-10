import { observarEncuadre, useMedidasEstables } from './encuadre';
import { textoNivelAprox } from './plantaSimulada';
import { CatalogoBoton } from './catalogo/CatalogoBoton';
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, ReactFlowProvider, getStraightPath, useEdges, useNodeId, useReactFlow, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import { WaterSupplyNode } from './WaterSupplyNode';
import { CatalogEndNode, CatalogJunctionNode, CatalogPumpNode, CatalogValveNode } from './CatalogParts';
import { InstrumentTag, tagSize } from './InstrumentTag';

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
  /** true en planta REAL: el nivel de T1 se dibuja con los switches (no hay sensor) */
  nivelAprox?: boolean;
}

const T2_LABEL_SIZE = tagSize(['TRANSMISOR DE PRESIÓN', 'PRESOSTATO'], 8);

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
  const label = `VÁLVULA PROPORCIONAL · ${pct == null ? 'SIN DATO' : `${pct} %`}`;
  const labelSize = tagSize([label], 11, 40);
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
      <div style={{ position: 'absolute', left: 35, top: -58, transform: 'translateX(-50%)', zIndex: 2, pointerEvents: 'none' }}>
        <InstrumentTag label={label} size={labelSize} maxChars={40} />
      </div>
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
        <svg width="220" height="100" viewBox="0 0 220 100" aria-hidden>
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
          <g transform="translate(220 0) scale(-1 1)">
          <rect x="165" y="0" width="10" height="20" className="v-pipe" />
          <rect x="194" y="45" width="26" height="10" className="v-pipe" />
          <rect x="0" y="22" width="102" height="56" rx="8" fill="url(#pr-g-motor)" />
          {[14, 26, 38, 50, 62, 74, 86].map((x) => (
            <line key={x} x1={x} y1="26" x2={x} y2="74" stroke="#0e1a66" strokeWidth="2" opacity=".55" />
          ))}
          <rect x="102" y="32" width="14" height="36" fill="#7b8794" />
          <rect x="116" y="18" width="80" height="64" rx="12" fill="url(#pr-g-casing)" />
          <g className={on ? 'impeller impeller--on' : 'impeller'} style={{ transformBox: 'fill-box', transformOrigin: 'center' }}>
            <circle cx="156" cy="50" r="19" fill="#d5dce3" stroke="#8795a3" strokeWidth="2" />
            {[0, 60, 120, 180, 240, 300].map((a) => (
              <line key={a} x1="156" y1="50" x2="156" y2="34" stroke="#5b6b7d" strokeWidth="3" strokeLinecap="round" transform={`rotate(${a} 156 50)`} />
            ))}
          </g>
          <circle cx="12" cy="12" r="5" className={on && known ? 'led led--on' : 'led'} />
          </g>
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
      <div className="tank__readout"><strong>{pct == null ? '—' : d.aprox === true ? textoNivelAprox(pct) : pct.toFixed(0)}</strong><span>{pct == null ? 'sin dato' : d.aprox === true ? 'nivel' : '%'}</span></div>
      <span className="tag level-tag" style={{ right: 204, top: 42 }}>NIVEL ALTO <i className={alto ? 'led led--alarm' : 'led'} /></span>
      <span className="tag level-tag" style={{ right: 204, top: 260 }}>NIVEL BAJO <i className={bajo ? 'led led--alarm' : 'led'} /></span>
      <span className="tag" style={{ left: 60, top: 10 }}>TANQUE T1</span>
      <Port id="in" position={Position.Top} style={{ left: 81 }} />
      <Port id="inR" position={Position.Top} style={{ left: 150 }} />
      <Port id="out" position={Position.Bottom} style={{ left: 98 }} />
    </div>
  );
}

function TransmisorPresionT2() {
  return (
    <div style={{ width: 48, height: 62, position: 'relative' }} title="Transmisor de presión">
      <svg width="48" height="62" viewBox="0 0 104 134" aria-hidden>
        <rect x="12" y="10" width="80" height="70" rx="16" fill="#1f8fd8" stroke="#0f5f96" strokeWidth="2" />
        <rect x="38" y="80" width="28" height="16" rx="3" fill="#1f8fd8" stroke="#0f5f96" strokeWidth="2" />
        <rect x="40" y="96" width="24" height="10" rx="2" fill="#b8c0c8" stroke="#8a949e" />
        <rect x="45" y="106" width="14" height="16" fill="#9aa4ae" stroke="#7d8791" />
        <path d="M45 111h14M45 115h14M45 119h14" stroke="#7d8791" fill="none" />
        <circle cx="52" cy="45" r="33" fill="#e9ecef" stroke="#b9c0c7" strokeWidth="2" />
        <circle cx="52" cy="45" r="27" fill="#f6f7f8" stroke="#d5dadf" />
        <rect x="33" y="30" width="38" height="22" rx="3" fill="#8fe36f" stroke="#1b2a20" strokeWidth="2" />
        {[33, 47.5, 62].map((x) => <rect key={x} x={x} y="57" width="9" height="8" rx="1.5" fill="#2b3138" />)}
      </svg>
    </div>
  );
}

function PresostatoT2() {
  return (
    <div style={{ width: 56, height: 51, position: 'relative' }} title="Presostato">
      <svg width="56" height="51" viewBox="0 16 120 110" aria-hidden>
        <rect x="10" y="20" width="100" height="74" rx="8" fill="#f4f5f6" stroke="#c8ced4" strokeWidth="2" />
        <rect x="16" y="26" width="88" height="62" rx="6" fill="none" stroke="#dde1e5" />
        <rect x="34" y="32" width="38" height="44" rx="2" fill="#12161a" />
        <path d="M40 38h5M40 44h5M40 50h5M40 56h5M40 62h5M40 68h5M56 38h5M56 44h5M56 50h5M56 56h5" stroke="#cfd6dc" strokeWidth="1.2" fill="none" />
        <rect x="46" y="48" width="3" height="10" fill="#cfd6dc" />
        <rect x="62" y="44" width="3" height="8" fill="#cfd6dc" />
        <ellipse cx="90" cy="92" rx="6" ry="2.5" fill="#3a3f44" />
        <rect x="48" y="94" width="24" height="12" rx="2" fill="#d4aa3a" stroke="#9a7a1f" />
        <rect x="52" y="106" width="16" height="16" fill="#c79a2c" stroke="#9a7a1f" />
        <path d="M52 111h16M52 115h16M52 119h16" stroke="#9a7a1f" fill="none" />
      </svg>
    </div>
  );
}

function TankT2Node({ data }: NodeProps) {
  const d = data as Data;
  const psi = typeof d.psi === 'number' ? d.psi : null;
  return (
    <div className="tank" style={{ width: 130, height: 350 }}>
      <SteelTank w={130} h={350} fill={psi == null ? null : Math.min(90, 30 + psi * 0.8)} id="prt2" />
      <div style={{ position: 'absolute', left: 6, top: -56, zIndex: 2, pointerEvents: 'none' }}>
        <TransmisorPresionT2 />
      </div>
      <div style={{ position: 'absolute', left: 74, top: -49, zIndex: 2, pointerEvents: 'none' }}>
        <PresostatoT2 />
      </div>
      <div className="psi"><span>Presión (PSI)</span><strong>{psi == null ? '—' : psi.toFixed(0)}</strong></div>
      <span className="tag" style={{ left: 36, top: 150 }}>TANQUE T2</span>
      <div style={{ position: 'absolute', left: 30, top: -84, transform: 'translateX(-50%)', zIndex: 2, pointerEvents: 'none' }}>
        <InstrumentTag label="TRANSMISOR DE PRESIÓN" size={T2_LABEL_SIZE} />
      </div>
      <div style={{ position: 'absolute', left: 102, top: -77, transform: 'translateX(-50%)', zIndex: 2, pointerEvents: 'none' }}>
        <InstrumentTag label="PRESOSTATO" size={T2_LABEL_SIZE} />
      </div>
      <Port id="inR" position={Position.Right} style={{ top: 320 }} />
      <Port id="air1" position={Position.Right} style={{ top: 70 }} />
      <Port id="air2" position={Position.Right} style={{ top: 86 }} />
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
const valve = (valveId: string, cx: number, cy: number, orientation: 'h' | 'v', nominal: boolean, tag?: string): Node => ({
  id: valveId, type: 'valve', ...fixed,
  position: orientation === 'h' ? { x: cx - 35, y: cy - 20 } : { x: cx - 20, y: cy - 35 },
  data: { valveId, label: valveId, orientation, nominal, ...(orientation === 'h' ? { pressureTag: true, tagSide: 'r' } : {}), ...(tag ? { tag } : {}) },
});
const end = (id: string, x: number, y: number, side: 'r' | 't'): Node => ({ id, type: 'end', position: { x, y }, data: { side }, ...fixed });

const BASE_NODES: Node[] = [
  { id: 'pump', type: 'pump', position: { x: 785, y: 1628 }   /* más abajo: deja espacio al tramo V6/JD → bomba */, data: { mirror: true, air: true }, ...fixed },
  { id: 't1', type: 'tankT1', position: { x: 307, y: 1020 }, data: {}, ...fixed },
  { id: 't2', type: 'tankT2', position: { x: 622, y: 840 }, data: {}, ...fixed },
  { id: 'ac', type: 'charger', position: { x: 760, y: 885 }   /* arriba, junto a la cámara de aire de T2 */, data: {}, ...fixed },
  { id: 'PV', type: 'propValve', position: { x: 445, y: 645 }, data: {}, ...fixed },
  /* Posición nominal: V2, V5 abiertas · V1, V3, V4, V6, V7 cerradas */
  valve('V1', 300, 948, 'h', false, 'lever-top-h'), valve('V2', 388, 865, 'v', true, 'lever-top-v'), valve('V3', 300, 785, 'h', false), valve('V4', 770, 1320, 'h', false, 'side-right'),
  valve('V5', 835, 1420, 'v', true, 'lever-right'), valve('V6', 760, 1520, 'h', false),
  valve('V7', 405, 1740, 'v', false, 'left'),   /* descarga de T1: la tubería termina en la llave (bota el agua) */
  valve('VF', 145, 1480, 'h', false),            /* llave de la fuente, pegada a su pico */
  junction('JTL', 388, 665), junction('JV3', 388, 785), junction('JV1', 388, 948),
  junction('JLt2', 553, 985), junction('JLb2', 553, 1520), junction('JU', 585, 665), junction('JRB', 585, 1160),
  junction('JR2', 457, 985),
  junction('JT', 405, 1678), junction('JD', 835, 1520), junction('J4', 835, 1320), junction('JE', 835, 1160),
  junction('JF', 95, 948), junction('JFB', 95, 1480),
  end('END3', 253, 773, 'r'), end('END4', 723, 1308, 'r'),
  { id: 'SUPPLY', type: 'supply', position: { x: 187, y: 1422 }, data: { side: 'l' }, ...fixed },
];

const ed = (id: string, source: string, sh: string, target: string, th: string, type: 'pipe' | 'hose' = 'pipe'): Edge => ({
  id, source, sourceHandle: sh, target, targetHandle: th, type, data: { active: false },
});

const EDGES: Edge[] = [
  ed('o1', 't1', 'out', 'JT', 't'), ed('o2', 'JT', 'r', 'pump', 'suction'),
  /* llenado de T1: fuente → VF → sube → V1 → T1 */
  ed('o4', 'SUPPLY', 'l', 'VF', 'r'),
  ed('o5', 'VF', 'l', 'JFB', 'r'),
  ed('o6', 'JFB', 't', 'JF', 'b'),
  ed('o7', 'JF', 'r', 'V1', 'l'),
  /* descarga de T1 por V7 */
  ed('d1', 'JT', 'b', 'V7', 't'),
  ed('u1', 'pump', 'discharge', 'JD', 'b'),
  ed('l1', 'JD', 'l', 'V6', 'r'), ed('l2', 'V6', 'l', 'JLb2', 'r'), ed('l3', 'JLb2', 't', 'JLt2', 'b'),
  ed('l4', 'JLt2', 'l', 'JR2', 'r'), ed('l5', 'JR2', 'b', 't1', 'inR'),
  ed('t1', 'JD', 't', 'V5', 'b'), ed('t2', 'V5', 't', 'J4', 'b'), ed('t3', 'J4', 't', 'JE', 'b'),
  ed('t4', 'JE', 'l', 't2', 'inR'), ed('t6a', 'ac', 'o1', 't2', 'air1'), ed('t6b', 'ac', 'o2', 't2', 'air2'),
  ed('h1', 'pump', 'air', 'ac', 'b', 'hose'),
  ed('s1', 'J4', 'l', 'V4', 'r'), ed('s2', 'V4', 'l', 'END4', 'r'),
  ed('r1', 't2', 'outL', 'JRB', 'r'), ed('r2', 'JRB', 't', 'JU', 'b'), ed('r3', 'JU', 'l', 'PV', 'r'),
  ed('r4', 'PV', 'l', 'JTL', 'r'), ed('r5', 'JTL', 'b', 'JV3', 't'),
  ed('v1', 'JV3', 'l', 'V3', 'r'), ed('v2', 'V3', 'l', 'END3', 'r'),
  ed('v3', 'JV3', 'b', 'V2', 't'), ed('v4', 'V2', 'b', 'JV1', 't'),
  ed('f2', 'V1', 'r', 'JV1', 'l'),
  ed('n1', 'JV1', 'b', 't1', 'in'),
];

/* Válvulas que gobiernan cada tramo: si alguna está cerrada, el agua no circula por él. */
const EDGE_VALVE: Record<string, string[]> = {
  o4: ['VF'], o5: ['VF'], o6: ['VF'], o7: ['VF'], f2: ['VF', 'V1'],
  d1: ['V7'],
  l1: ['V6'], l2: ['V6'], l3: ['V6'], l4: ['V6'], l5: ['V6'],
  s1: ['V4'], s2: ['V4'],
  t1: ['V5'], t2: ['V5'], t3: ['V5'], t4: ['V5'],
  v1: ['V3'], v2: ['V3'],
  v3: ['V2'], v4: ['V2'], n1: ['V2'],
};
/* Tramos que mueve la bomba vs. los que mueve la presión de T2 (retorno) vs. gravedad/fuente. */
const POR_BOMBA = new Set(['o1', 'o2', 'u1', 'h1', 't1', 't2', 't3', 't4', 't6a', 't6b', 'l1', 'l2', 'l3', 'l4', 'l5', 's1', 's2']);
const FUENTE = new Set(['o4', 'o5', 'o6', 'o7', 'f2']);
const POR_RETORNO = new Set(['r1', 'r2', 'r3', 'r4', 'r5', 'v1', 'v2', 'v3', 'v4', 'n1']);

const HORIZONTAL_TAG_PLAN = { open: 'top', closed: 'right', unknown: 'right' } as const;
const VERTICAL_TAG_PLAN = { open: 'top', closed: 'top', unknown: 'top' } as const;
const TAG_PLAN = {
  V1: HORIZONTAL_TAG_PLAN,
  V2: VERTICAL_TAG_PLAN,
  V3: HORIZONTAL_TAG_PLAN,
  V4: HORIZONTAL_TAG_PLAN,
  V5: VERTICAL_TAG_PLAN,
  V6: HORIZONTAL_TAG_PLAN,
  V7: VERTICAL_TAG_PLAN,
  VF: HORIZONTAL_TAG_PLAN,
} as const;

const edgeTypes = { pipe: PipeEdge, hose: HoseEdge };

/* ───────────── Lienzo con re-encaje automático ───────────── */
function Flow({ senal, interactivo = false, onValvulas, onLlave }: { senal: PresionSenal; interactivo?: boolean; onValvulas?: (v: Record<string, boolean | null>) => void; onLlave?: (id: string, abierta: boolean) => void }) {
  const rf = useReactFlow();
  const ref = useRef<HTMLDivElement>(null);
  /* SIMULADOR: las llaves se abren/cierran con clic (solo visual, nunca órdenes al PLC). En REAL son fijas. */
  const [manual, setManual] = useState<Record<string, boolean>>({});
  const abierta = (id: string): boolean | null => {
    if (interactivo && id in manual) return manual[id];
    const nodo = BASE_NODES.find((x) => x.id === id);
    const nom = (nodo?.data as Data | undefined)?.nominal;
    return senal.valvulas[id] ?? (typeof nom === 'boolean' ? nom : null);
  };
  /* SIMULADOR del navegador: estado local. PLANTA SIMULADA (onLlave): la llave la mueve el simulador Python. */
  const alternar = (id: string) => {
    if (interactivo) setManual((m) => ({ ...m, [id]: !(abierta(id) === true) }));
    else onLlave?.(id, !(abierta(id) === true));
  };
  const clicable = interactivo || !!onLlave;
  const IDS_VALV = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'VF'];
  const firmaValv = IDS_VALV.map((v) => String(abierta(v))).join(',');
  useEffect(() => {
    onValvulas?.(Object.fromEntries(IDS_VALV.map((v) => [v, abierta(v)])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firmaValv]);

  const nodes = useMemo<Node[]>(() => {
    const activo = senal.online && senal.bomba === true;
    return BASE_NODES.map((n) => {
      const data: Data = { ...n.data };
      if (n.type === 'pump') data.on = senal.bomba;
      if (n.type === 'tankT1') { data.aprox = senal.nivelAprox === true; data.nivelPct = senal.nivelPct; data.alto = senal.nivelAlto; data.bajo = senal.nivelBajo; }
      if (n.type === 'tankT2') data.psi = senal.presion;
      if (n.type === 'propValve') data.pct = senal.valvulaPct;
      if (n.type === 'valve') {
        const nom = (n.data as Data).nominal;
        void nom;
        data.open = abierta(String(n.id));
        if (clicable) data.onToggle = () => alternar(String(n.id));
        data.tagPlan = TAG_PLAN[String(n.id) as keyof typeof TAG_PLAN];
      }
      if (n.type === 'supply') data.active = (interactivo || senal.online) && abierta('VF') === true;
      if (n.type === 'end') data.active = activo;
      return { ...n, data };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [senal, manual, interactivo, onLlave]);

  const edges = useMemo<Edge[]>(() => EDGES.map((e) => {
    const gates = EDGE_VALVE[e.id] ?? [];
    const abiertas = gates.every((g) => abierta(g) === true);
    const motor = POR_BOMBA.has(e.id) ? senal.bomba === true
      : POR_RETORNO.has(e.id) ? (senal.presion ?? 0) > 0.5 && (senal.valvulaPct ?? 0) > 0
      : true;
    /* Tramos de la fuente (VF → V1 → T1) y de la descarga V7: van por gravedad/red, no dependen del PLC.
       El agua avanza hasta la primera llave cerrada: con V1 cerrada se queda en V1. */
    const llenando = abierta('VF') === true && abierta('V1') === true;
    let active: boolean;
    if (e.id === 'n1') active = llenando || (senal.online && abiertas && motor);       // JV1 → T1: llenado o retorno por V2
    else if (FUENTE.has(e.id)) active = (interactivo || senal.online) && abiertas;
    else if (e.id === 'd1') active = (interactivo || senal.online) && abiertas && (senal.nivelPct ?? 0) > 0.5;
    else active = senal.online && abiertas && motor;
    return { ...e, data: { active } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [senal, manual, interactivo]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = observarEncuadre(el, () => void rf.fitView({ padding: 0.2 }));
    return () => ro.disconnect();
  }, [rf]);

  const estables = useMedidasEstables(nodes);   // evita que los nodos queden ocultos tras cada dato en vivo

  return (
    <div className="ca-canvas" ref={ref}>
      <ReactFlow nodes={estables.nodes} onNodesChange={estables.onNodesChange} edges={edges} onNodeClick={(_, n) => { if (clicable && n.type === 'valve') alternar(n.id); }} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3} maxZoom={2} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}>
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.2} />
        <Controls showInteractive={false} position="top-right" fitViewOptions={{ padding: 0.2 }}><CatalogoBoton /></Controls>
      </ReactFlow>
    </div>
  );
}

export function PressureFlow({ senal, interactivo = false, onValvulas, onLlave }: { senal: PresionSenal; interactivo?: boolean; onValvulas?: (v: Record<string, boolean | null>) => void; onLlave?: (id: string, abierta: boolean) => void }) {
  return (
    <ReactFlowProvider>
      <Flow key={interactivo ? 'sim' : 'real'} senal={senal} interactivo={interactivo} onValvulas={onValvulas} onLlave={onLlave} />
    </ReactFlowProvider>
  );
}
