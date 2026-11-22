import { observarEncuadre, useMedidasEstables } from './encuadre';
import { textoNivelAprox } from './plantaSimulada';
import { CatalogoBoton } from './catalogo/CatalogoBoton';
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, ReactFlowProvider, getStraightPath, useEdges, useNodeId, useReactFlow, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import { InstrumentTag, tagSize } from './InstrumentTag';
import { tagStyle as tagStyleCatalogo } from './catalogo/valveTagCatalogo';
import { PumpTag } from './PumpTag';

/* ============================================================
   Diagrama mímico de CAUDAL (MCC-09) — puerto de BOSETOS/scada-flow
   100 % solo lectura: ningún nodo emite órdenes al PLC.
   Los valores llegan como props; sin dato real se pintan «SIN DATO».
   ============================================================ */

type Data = Record<string, unknown>;

export interface CaudalSenal {
  online: boolean;
  caudal: number | null;      // flujómetro L/min
  presion: number | null;     // manómetro
  nivelPct: number | null;    // nivel tanque T1 0-100 %
  bomba: boolean | null;
  valvulaPct: number | null;  // válvula proporcional %
  valvulas: Record<string, boolean | null>;
  nivelAlto: boolean | null;
  nivelBajo: boolean | null;
  /** true en planta REAL: el nivel de T1 se dibuja con los switches (no hay sensor) */
  nivelAprox?: boolean;
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
type Box = [number, number, number, number];
const ARM: Record<string,{body:Box;flange:Box}>={l:{body:[2,17,20,10],flange:[0,13,5,18]},r:{body:[22,17,20,10],flange:[39,13,5,18]},t:{body:[17,2,10,20],flange:[13,0,18,5]},b:{body:[17,22,10,20],flange:[13,39,18,5]}};
function JunctionNode() {
  const id=useNodeId(); const all=useEdges();
  const mine=all.filter(e=>e.source===id||e.target===id);
  const arms=[...new Set(mine.map(e=>e.source===id?e.sourceHandle:e.targetHandle).filter((h):h is string=>!!h))];
  return (
    <div className="junction">
      {arms.length>=2&&<svg width="44" height="44" viewBox="0 0 44 44" className="ca-fitting" aria-hidden><g className="ca-fit-outline">{arms.map(a=>ARM[a]&&<g key={a}><rect x={ARM[a].body[0]} y={ARM[a].body[1]} width={ARM[a].body[2]} height={ARM[a].body[3]}/><rect x={ARM[a].flange[0]} y={ARM[a].flange[1]} width={ARM[a].flange[2]} height={ARM[a].flange[3]} rx="1.5"/></g>)}<rect x="12" y="12" width="20" height="20" rx="4"/></g><g className="ca-fit-body">{arms.map(a=>ARM[a]&&<g key={a}><rect x={ARM[a].body[0]} y={ARM[a].body[1]} width={ARM[a].body[2]} height={ARM[a].body[3]}/><rect x={ARM[a].flange[0]} y={ARM[a].flange[1]} width={ARM[a].flange[2]} height={ARM[a].flange[3]} rx="1.5"/></g>)}<rect x="12" y="12" width="20" height="20" rx="4"/></g></svg>}
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
  const side = String(d.side) as 'l' | 't';
  return (
    <div className={`pipe-end pipe-end--${side}`}>
      <div className="pipe-end__flange" />
      <Port id={side} position={side === 'l' ? Position.Left : Position.Top} />
    </div>
  );
}

/* ───────────── Válvula de bola (solo lectura) — estilo idéntico a scada-parts-codos-tes ───────────── */
function ValveGlyph({ open }: { open: boolean | null }) {
  const cls = open === true ? 'v-body v-body--open' : open === false ? 'v-body v-body--closed' : 'v-body v-body--unknown';
  return (
    <svg width="70" height="40" viewBox="0 0 70 40" overflow="visible" aria-hidden>
      <rect x="0" y="15" width="70" height="10" className="v-pipe" />
      <rect x="22" y="12" width="26" height="16" rx="3" className="v-flange" />
      <circle cx="35" cy="20" r="10" className={cls} />
      <line x1="35" y1="10" x2="35" y2="6" className="v-stem" />
      <rect
        x="33" y="3" width="30" height="5" rx="2.5" className="v-lever"
        style={{ transformOrigin: '35px 5.5px', transform: `rotate(${open ? 0 : -90}deg)` }}
      />
    </svg>
  );
}

function ValveNode({ data }: NodeProps) {
  const d = data as Data;
  const orientation = String(d.orientation) as 'h' | 'v';
  const open = (d.open as boolean | null) ?? null;
  const vertical = orientation === 'v';
  const left = vertical && (d.valveId === 'V5' || d.leverLeft === true);
  return (
    <div className={typeof d.onToggle === 'function' ? 'valve nodrag nopan valve--manual' : 'valve nodrag nopan'}
      title={typeof d.onToggle === 'function' ? 'Clic para abrir/cerrar (solo visual, no es una orden al PLC)' : 'Solo lectura · sin órdenes al PLC'}
      style={{ width: vertical ? 40 : 70, height: vertical ? 70 : 40, cursor: typeof d.onToggle === 'function' ? 'pointer' : undefined }}>
      <div
        className="valve__hit"
        style={vertical
          ? { left: -15, top: 15, width: 70, height: 40, transform: left ? 'rotate(270deg)' : 'rotate(90deg)' }  /* misma geometría que el catálogo */
          : { left: 0, top: 0, width: 70, height: 40 }}
      >
        <ValveGlyph open={open} />
      </div>
      {/* rótulo con la regla del catálogo: se mueve (con transición) según la palanca abierta/cerrada */}
      <span className="valve__tag" style={tagStyleCatalogo(vertical, 'top', open, left, String(d.label ?? 'V1'))}>
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
    <div className="valve" title="Solo lectura · sin órdenes al PLC" style={{ width: 70, height: 40 }}>
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

/* ───────────── Instrumento de dial (flujómetro / manómetro) ───────────── */
function GaugeNode({ data }: NodeProps) {
  const d = data as Data;
  const label = String(d.label ?? '');
  const size = Number(d.size) || 100;
  const inline = d.inline === true;
  const value = typeof d.value === 'number' ? d.value : null;
  const shown = value ?? 0;
  const ang = (v: number) => -120 + (Math.min(80, Math.max(0, v)) / 80) * 240;
  const digital = d.kind === 'flow';
  const pct = Math.min(1, Math.max(0, shown / 80));

  return (
    <div className="gauge" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox="0 0 100 100" role="img" aria-label={`${label}: ${value == null ? 'sin datos' : shown.toFixed(2)}`}>
        {digital ? (
          <>
            <rect x="2" y="2" width="96" height="96" rx="10" fill="#1a2733" stroke="#6f8193" strokeWidth="3" />
            <rect x="10" y="14" width="80" height="46" rx="5" fill="#06121a" stroke="#0b2a3a" strokeWidth="1.5" />
            <text x="50" y="45" textAnchor="middle" fontFamily="monospace" fontWeight="700" fontSize="22" fill="#7ff0ff" opacity="0.07">88.88</text>
            <text x="50" y="45" textAnchor="middle" fontFamily="monospace" fontWeight="700" fontSize="22" fill={value == null ? '#4a5b69' : '#7ff0ff'}>
              {value == null ? '---' : shown.toFixed(2)}
            </text>
            <text x="50" y="56" textAnchor="middle" fontFamily="monospace" fontWeight="700" fontSize="8" fill="#4cc3f2">
              {value == null ? 'SIN DATO' : 'L/min'}
            </text>
            <rect x="14" y="70" width="72" height="8" rx="4" fill="#06121a" stroke="#0b2a3a" />
            <rect x="14" y="70" width={72 * pct} height="8" rx="4" fill="#4cc3f2" style={{ transition: 'width .5s ease-out' }} opacity={value == null ? 0.25 : 1} />
            <text x="14" y="92" fontFamily="monospace" fontSize="8" fill="#8da2b3">0</text>
            <text x="86" y="92" textAnchor="end" fontFamily="monospace" fontSize="8" fill="#8da2b3">80</text>
          </>
        ) : (
          <>
            <circle cx="50" cy="50" r="47" className="dial__face" />
            {Array.from({ length: 17 }, (_, i) => i * 5).map((v) => (
              <line key={v} x1="50" x2="50" y1="6" y2={v % 20 === 0 ? 15 : 11} className="dial__tick" transform={`rotate(${ang(v)} 50 50)`} />
            ))}
            {[0, 20, 40, 60, 80].map((v) => (
              <text key={v} className="dial__num" textAnchor="middle" x={50 + 31 * Math.sin((ang(v) * Math.PI) / 180)} y={53 - 31 * Math.cos((ang(v) * Math.PI) / 180)}>{v}</text>
            ))}
            <g style={{ transform: `rotate(${ang(shown)}deg)`, transformOrigin: '50px 50px', transition: 'transform .5s ease-out', opacity: value == null ? 0.25 : 1 }}>
              <line x1="50" y1="52" x2="50" y2="17" className="dial__needle" />
            </g>
            <circle cx="50" cy="50" r="5" className="dial__hub" />
            <text x="50" y="82" textAnchor="middle" className="dial__value">{value == null ? 'SIN DATO' : shown.toFixed(0)}</text>
          </>
        )}
      </svg>
      <span
        className="tag"
        style={digital
          ? { left: '50%', transform: 'translateX(-50%)', top: -29, whiteSpace: 'nowrap', padding: '6px 7px', lineHeight: 1 }
          : { left: 0, top: -24, whiteSpace: 'nowrap' }}
      >
        {label}
      </span>
      {inline ? (
        <>
          <Port id="t" position={Position.Top} />
          <Port id="b" position={Position.Bottom} />
        </>
      ) : (
        <Port id="l" position={Position.Left} />
      )}
    </div>
  );
}

/* ───────────── Bomba con motor ───────────── */
function PumpNode({ data }: NodeProps) {
  const d = data as Data;
  const on = d.on === true;
  const known = d.on !== null && d.on !== undefined;
  return (
    <div className="pump nodrag nopan" title="Solo lectura · sin órdenes al PLC" style={{ width: 220, height: 100 }}>
      <div className="pump__hit">
        <svg width="220" height="100" viewBox="0 0 220 100" aria-hidden>
          <defs>
            <linearGradient id="ca-g-motor" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#3b6bff" />
              <stop offset="1" stopColor="#1b2fa8" />
            </linearGradient>
            <linearGradient id="ca-g-casing" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#f4f6f8" />
              <stop offset="1" stopColor="#aab4be" />
            </linearGradient>
          </defs>
          <rect x="165" y="0" width="10" height="20" className="v-pipe" />
          <rect x="194" y="45" width="26" height="10" className="v-pipe" />
          <rect x="0" y="22" width="102" height="56" rx="8" fill="url(#ca-g-motor)" />
          {[14, 26, 38, 50, 62, 74, 86].map((x) => (
            <line key={x} x1={x} y1="26" x2={x} y2="74" stroke="#0e1a66" strokeWidth="2" opacity=".55" />
          ))}
          <rect x="102" y="32" width="14" height="36" fill="#7b8794" />
          <rect x="116" y="18" width="80" height="64" rx="12" fill="url(#ca-g-casing)" />
          <g className={on ? 'impeller impeller--on' : 'impeller'}>
            <circle cx="156" cy="50" r="19" fill="#d5dce3" stroke="#8795a3" strokeWidth="2" />
            {[0, 60, 120, 180, 240, 300].map((a) => (
              <line key={a} x1="156" y1="50" x2="156" y2="34" stroke="#5b6b7d" strokeWidth="3" strokeLinecap="round" transform={`rotate(${a} 156 50)`} />
            ))}
          </g>
        </svg>
      </div>
      <div style={{ position: 'absolute', left: 51, top: 12, transform: 'translate(-50%,-100%)', zIndex: 3, pointerEvents: 'none' }}>
        <PumpTag on={on} known={known} />
      </div>
      <Port id="discharge" position={Position.Top} style={{ left: 170 }} />
      <Port id="suction" position={Position.Right} />
    </div>
  );
}

/* ───────────── Tanque T1 con switches de nivel ───────────── */
const TW = 195;
const TH = 255;

function TankNode({ data }: NodeProps) {
  const d = data as Data;
  const pct = typeof d.levelPct === 'number' ? d.levelPct : null;
  const y = TH - ((Math.min(100, Math.max(0, pct ?? 0)) / 100) * TH);
  const high = d.alto === true;
  const bajo = d.bajo === true;
  return (
    <div className="tank" style={{ width: TW, height: TH }}>
      <svg width={TW} height={TH} viewBox={`0 0 ${TW} ${TH}`} overflow="visible" role="img" aria-label={`Nivel del tanque ${pct == null ? 'sin datos' : pct.toFixed(0)}`}>
        <defs>
          <clipPath id="ca-tank-clip"><rect width={TW} height={TH} rx="16" /></clipPath>
          <linearGradient id="ca-g-steel" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#59606a" /><stop offset=".25" stopColor="#b9c0c8" />
            <stop offset=".45" stopColor="#eef1f4" /><stop offset=".75" stopColor="#8f98a2" /><stop offset="1" stopColor="#4f565f" />
          </linearGradient>
          <linearGradient id="ca-g-water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#4cc3f2" stopOpacity=".95" /><stop offset="1" stopColor="#136ea3" stopOpacity=".95" />
          </linearGradient>
        </defs>
        <rect width={TW} height={TH} rx="16" fill="url(#ca-g-steel)" />
        <g clipPath="url(#ca-tank-clip)" opacity=".72">
          <g style={{ transform: `translateY(${pct == null ? TH : y}px)`, transition: 'transform .5s ease-out' }}>
            <path className="tank__wave" fill="url(#ca-g-water)" d="M0 0 q28 -7 56 0 t56 0 t56 0 t56 0 t56 0 t56 0 t56 0 t56 0 V300 H0 Z" />
          </g>
        </g>
        <rect width={TW} height={TH} rx="16" fill="none" stroke="#2a323b" strokeWidth="2" />
        <rect x="-10" y="33" width="14" height="16" rx="3" className={high ? 'level-switch-orange on' : 'level-switch-orange'} />
        <rect x="-10" y="213" width="14" height="16" rx="3" className={bajo ? 'level-switch-orange on' : 'level-switch-orange'} />
      </svg>
      <div className="tank__readout"><strong>{pct == null ? '—' : d.aprox === true ? textoNivelAprox(pct) : pct.toFixed(0)}</strong><span>{pct == null ? 'sin dato' : d.aprox === true ? 'nivel' : '%'}</span></div>
      <span className="tag level-tag" style={{ right: TW + 14, top: 41 }}>NIVEL ALTO <i className={high ? 'led led--alarm' : 'led'} /></span>
      <span className="tag level-tag" style={{ right: TW + 14, top: 221 }}>NIVEL BAJO <i className={bajo ? 'led led--alarm' : 'led'} /></span>
      <span className="tag tank__name" style={{ left: TW / 2, top: 34, transform: 'translateX(-50%)', whiteSpace: 'nowrap' }}>TANQUE T1</span>
      <Port id="inL" position={Position.Top} style={{ left: 90 }} />
      <Port id="inR" position={Position.Top} style={{ left: 120 }} />
      <Port id="out" position={Position.Bottom} style={{ left: 103 }} />
    </div>
  );
}

/* Fuente externa representada, sin sensor propio en el PLC. */
function WaterSupplyNode({ data }: NodeProps) {
  const d=data as Data; const active=d.active===true;
  return <div className="water-supply" title="Representación del abastecimiento externo; no dispone de medición en el PLC">
    <svg width="200" height="118" viewBox="-10 -10 220 138" overflow="visible" aria-hidden>
      <rect x="25" y="24" width="150" height="68" rx="8" className="supply-tank" />
      <path d="M31 57q18-7 36 0t36 0t36 0t30 0v29H31z" className={active ? 'supply-water active' : 'supply-water'} />
      <rect x="84" y="4" width="32" height="22" rx="3" className="supply-neck" />
      <path d="M72 4h56M100 4V-8" className="supply-rim" />
    </svg>
    <b>ABASTECIMIENTO DE AGUA</b>
    <span>FUENTE EXTERNA · SALIDA SUPERIOR</span>
    <Port id="in" position={Position.Top} style={{left:100}} />
  </div>;
}

const nodeTypes = {
  junction: JunctionNode,
  end: EndNode,
  valve: ValveNode,
  propValve: ProportionalValveNode,
  gauge: GaugeNode,
  pump: PumpNode,
  tank: TankNode,
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

/* ───────────── Geometría (idéntica a BOSETOS/scada-flow) ───────────── */
const fixed = { draggable: false, selectable: false };
const junction = (id: string, cx: number, cy: number): Node => ({ id, type: 'junction', position: { x: cx - 1, y: cy - 1 }, data: {}, ...fixed });
const valve = (valveId: string, cx: number, cy: number, orientation: 'h' | 'v', nominal: boolean): Node => ({
  id: valveId, type: 'valve', ...fixed,
  position: orientation === 'h' ? { x: cx - 35, y: cy - 20 } : { x: cx - 20, y: cy - 35 },
  data: { valveId, label: valveId, orientation, nominal },
});
const end = (id: string, x: number, y: number, side: 'l' | 't'): Node => ({ id, type: 'end', position: { x, y }, data: { side }, ...fixed });

const BASE_NODES: Node[] = [
  { id: 'pump', type: 'pump', position: { x: 270, y: 1213 }, data: {}, ...fixed },
  { id: 'FM', type: 'gauge', position: { x: 390, y: 1030 }, data: { kind: 'flow', label: 'FLUJÓMETRO', size: 100, inline: true }, ...fixed },
  { id: 'PG', type: 'gauge', position: { x: 468, y: 632 }, data: { kind: 'pressure', label: 'MANÓMETRO', size: 70, inline: false }, ...fixed },
  { id: 'tank', type: 'tank', position: { x: 625, y: 930 }, data: {}, ...fixed },
  { id: 'PV', type: 'propValve', position: { x: 560, y: 565 }, data: {}, ...fixed },
  { id: 'SUPPLY', type: 'supply', position: { x: 800, y: 1440 }, data: { portSide: 'l' }, ...fixed },
  /* Posición nominal según el manual INDUCONTROL del módulo: V2, V5 abiertas · V1, V3, V4, V6, V7 cerradas */
  valve('V1', 810, 888, 'h', false), valve('V2', 745, 650, 'v', true), valve('V3', 810, 770, 'h', false), valve('V4', 490, 775, 'h', false),
  valve('V5', 440, 830, 'v', true), valve('V6', 500, 888, 'h', false), { ...valve('V7', 728, 1325, 'v', false), data: { valveId: 'V7', label: 'V7', orientation: 'v', nominal: false, leverLeft: true } },  /* 180° · vertical · palanca izquierda */
  /* válvula manual en la boca de la fuente de agua (abre/cierra el abastecimiento hacia V1) */
  valve('VF', 900, 1404, 'v', true),   /* pegada al pico de la fuente, como en el módulo real */
  junction('JT', 728, 1263), junction('JV1F', 900, 888), junction('J888', 440, 888), junction('J775', 440, 775), junction('J667', 440, 667),
  junction('JTL', 440, 585), junction('JTR', 745, 585), junction('J640', 745, 770), junction('J888R', 745, 888), junction('JE', 715, 888),
  end('END3', 845, 758, 'l'), end('END4', 525, 763, 'l'),
];

const ed = (id: string, source: string, sh: string, target: string, th: string): Edge => ({
  id, source, sourceHandle: sh, target, targetHandle: th, type: 'pipe', data: { active: false },
});

const EDGES: Edge[] = [
  ed('o1', 'tank', 'out', 'JT', 't'), ed('o2', 'JT', 'l', 'pump', 'suction'),
  ed('o3', 'JT', 'b', 'V7', 't'),
  ed('u1', 'pump', 'discharge', 'FM', 'b'), ed('u2', 'FM', 't', 'J888', 'b'),
  ed('v1', 'J888', 'r', 'V6', 'l'), ed('v2', 'V6', 'r', 'JE', 'l'), ed('v3', 'JE', 'b', 'tank', 'inL'),
  ed('w1', 'J888', 't', 'V5', 'b'), ed('w2', 'V5', 't', 'J775', 'b'),
  ed('x1', 'J775', 'r', 'V4', 'l'), ed('x2', 'V4', 'r', 'END4', 'l'),
  ed('y1', 'J775', 't', 'J667', 'b'), ed('y2', 'J667', 't', 'JTL', 'b'), ed('y3', 'J667', 'r', 'PG', 'l'),
  ed('y4', 'JTL', 'r', 'PV', 'l'), ed('y5', 'PV', 'r', 'JTR', 'l'), ed('y6', 'JTR', 'b', 'V2', 't'),
  ed('z1', 'J640', 'r', 'V3', 'l'), ed('z2', 'V3', 'r', 'END3', 'l'),
  ed('z3', 'V2', 'b', 'J640', 't'), ed('z4', 'J640', 'b', 'J888R', 't'),   /* V2 arriba, ramal V3 debajo (como el módulo real) */ ed('z5', 'J888R', 'b', 'tank', 'inR'),
  /* abastecimiento: fuente → válvula manual VF → V1 → tanque */
  ed('s1', 'SUPPLY', 'in', 'VF', 'b'), ed('s2', 'VF', 't', 'JV1F', 'b'), ed('s3', 'JV1F', 'l', 'V1', 'r'),
  ed('f2', 'V1', 'l', 'J888R', 'r'),
];

const CAUDAL_TAG_PLAN = {
  V1: { open: 'top', closed: 'left', unknown: 'left' },
  V2: { open: 'right', closed: 'top', unknown: 'top' },
  V3: { open: 'top', closed: 'left', unknown: 'left' },
  V4: { open: 'top', closed: 'left', unknown: 'left' },
  V5: { open: 'right', closed: 'top', unknown: 'top' },
  V6: { open: 'top', closed: 'right', unknown: 'right' },
  V7: { open: 'right', closed: 'top', unknown: 'top' },
  VF: { open: 'right', closed: 'right', unknown: 'right' },
} as const;

const edgeTypes = { pipe: PipeEdge };

/* ───────────── Lienzo con re-encaje automático ───────────── */
export interface EstadoMimico { valvulas: Record<string, boolean | null>; nivelPct: number | null; nivelBajo: boolean | null }

function Flow({ senal, onEstado, interactivo = false, onLlave }: { senal: CaudalSenal; onEstado?: (e: EstadoMimico) => void; interactivo?: boolean; onLlave?: (id: string, abierta: boolean) => void }) {
  const ext = !interactivo && !!onLlave;   /* PLANTA SIMULADA: llaves y T1 del simulador Python */
  const rf = useReactFlow();
  const ref = useRef<HTMLDivElement>(null);
  /* Todas las llaves se abren/cierran con un clic, igual que en el catálogo.
     Es solo visual (no manda órdenes al PLC): el clic sobrescribe localmente el estado leído. */
  const [manual, setManual] = useState<Record<string, boolean>>({ VF: true, V7: false });
  const abierta = (id: string): boolean | null => {
    if (interactivo && id in manual) return manual[id];   // en REAL las llaves son manuales del módulo: el mímico no las mueve
    if (!interactivo && !ext && id === 'VF') return true;
    const nodo = BASE_NODES.find((x) => x.id === id);
    const nom = (nodo?.data as Data | undefined)?.nominal;
    return senal.valvulas[id] ?? (typeof nom === 'boolean' ? nom : null);
  };
  const alternar = (id: string) => {
    if (interactivo) setManual((m) => ({ ...m, [id]: !(abierta(id) === true) }));
    else if (ext) onLlave?.(id, !(abierta(id) === true));
  };
  const clicable = interactivo || ext;
  const fuenteAbierta = (interactivo || ext) && abierta('VF') === true;   // en REAL no hay medición de la fuente: sin animación

  /* ── Simulación visual del tanque T1 (solo cuando no hay nivel real del PLC) ──
     VF + V1 abiertas → entra agua; V7 abierta → drena.
     NIVEL BAJO activo con poca agua; al llegar a NIVEL ALTO se cierra V1 sola para que no rebalse. */
  const NIVEL_BAJO_PCT = 10, NIVEL_ALTO_PCT = 90;
  const usarSim = interactivo;   // SOLO en simulador se llena/drena el tanque virtual; en REAL el nivel viene del PLC
  const [nivelSim, setNivelSim] = useState(0);
  const [aviso, setAviso] = useState<string | null>(null);
  const llenando = fuenteAbierta && abierta('V1') === true;
  const drenando = abierta('V7') === true;
  useEffect(() => {
    if (!usarSim) return;
    const id = window.setInterval(() => {
      setNivelSim((n) => Math.max(0, Math.min(100, n + (llenando ? 1.2 : 0) - (drenando ? 0.9 : 0))));
    }, 200);
    return () => window.clearInterval(id);
  }, [usarSim, llenando, drenando]);
  useEffect(() => {
    if (usarSim && nivelSim >= NIVEL_ALTO_PCT && abierta('V1') === true) {
      setManual((m) => ({ ...m, V1: false }));
      setAviso('NIVEL ALTO · V1 se cerró sola para que el tanque no rebalse');
      const t = window.setTimeout(() => setAviso(null), 5000);
      return () => window.clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nivelSim, usarSim]);
  const nivelPct = usarSim ? nivelSim : senal.nivelPct;
  const nivelAlto = usarSim ? nivelSim >= NIVEL_ALTO_PCT : senal.nivelAlto;
  const nivelBajo = usarSim ? nivelSim <= NIVEL_BAJO_PCT : senal.nivelBajo;

  /* informa al SCADA (p. ej. al PLC virtual) cómo están las llaves y el tanque */
  const idsValvulas = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'VF'];
  const firma = idsValvulas.map((v) => String(abierta(v))).join(',') + '|' + Math.round(nivelPct ?? -1) + '|' + String(nivelBajo);
  useEffect(() => {
    onEstado?.({ valvulas: Object.fromEntries(idsValvulas.map((v) => [v, abierta(v)])), nivelPct: nivelPct ?? null, nivelBajo: nivelBajo ?? null });
  }, [firma]); // eslint-disable-line react-hooks/exhaustive-deps

  const nodes = useMemo<Node[]>(() => {
    const activo = senal.online && senal.bomba === true;
    return BASE_NODES.map((n) => {
      const data: Data = { ...n.data };
      if (n.type === 'pump') data.on = senal.bomba;
      if (n.type === 'gauge') data.value = data.kind === 'flow' ? senal.caudal : senal.presion;
      if (n.type === 'tank') { data.aprox = !usarSim && senal.nivelAprox === true; data.levelPct = nivelPct; data.alto = nivelAlto; data.bajo = nivelBajo; }
      if (n.type === 'supply') data.active = fuenteAbierta;
      if (n.type === 'propValve') data.pct = senal.valvulaPct;
      if (n.type === 'valve') {
        const nom = (n.data as Data).nominal;
        void nom;
        data.open = abierta(String(n.id));
        if (clicable) data.onToggle = () => alternar(String(n.id));
        data.tagPlan = CAUDAL_TAG_PLAN[String(n.id) as keyof typeof CAUDAL_TAG_PLAN];
      }
      if (n.type === 'end') data.active = activo;
      return { ...n, data };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [senal, manual, nivelPct, nivelAlto, nivelBajo]);

  const edges = useMemo<Edge[]>(() => EDGES.map((e) => {
    const pumpActive = senal.online && senal.bomba === true;
    const fuente = e.id === 's1';
    const haciaV1 = e.id === 's2' || e.id === 's3';
    const drenajeV7 = e.id === 'o3';
    const v6Branch = ['v1', 'v2', 'v3'].includes(e.id);
    const active = fuente || haciaV1
      ? fuenteAbierta            /* VF abierta: el agua sube de la fuente hasta V1 (se detiene ahí si V1 está cerrada) */
      : e.id === 'f2'
        ? fuenteAbierta && abierta('V1') === true
      : drenajeV7
        ? abierta('V7') === true
      : e.id === 'z5'
        ? pumpActive || llenando   /* entrada al tanque por la derecha (V1 o línea de la bomba) */
      : v6Branch
        ? pumpActive && abierta('V6') === true
        : pumpActive;
    return { ...e, data: { active } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [senal.online, senal.bomba, senal.valvulas, manual, llenando, interactivo]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = observarEncuadre(el, () => void rf.fitView({ padding: 0.2 }));
    return () => ro.disconnect();
  }, [rf]);

  const estables = useMedidasEstables(nodes);   // evita que los nodos queden ocultos tras cada dato en vivo

  return (
    <div className="ca-canvas" ref={ref}>
      {aviso && <div className="ca-aviso" role="alert">⚠ {aviso}</div>}
      <ReactFlow nodes={estables.nodes} onNodesChange={estables.onNodesChange} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={{ padding: 0.2 }}
        minZoom={0.15} maxZoom={2} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
        onNodeClick={(_, n) => { if (clicable && n.type === 'valve') alternar(n.id); }}>
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.2} />
        <Controls showInteractive={false} position="top-right" fitViewOptions={{ padding: 0.2 }}><CatalogoBoton /></Controls>
      </ReactFlow>
    </div>
  );
}

export function CaudalFlow({ senal, onEstado, interactivo = false, onLlave }: { senal: CaudalSenal; onEstado?: (e: EstadoMimico) => void; interactivo?: boolean; onLlave?: (id: string, abierta: boolean) => void }) {
  return (
    <ReactFlowProvider>
      {/* key: al cambiar REAL⇄SIMULADOR se reinicia el estado virtual (llaves, tanque) */}
      <Flow key={interactivo ? 'sim' : 'real'} senal={senal} onEstado={onEstado} interactivo={interactivo} onLlave={onLlave} />
    </ReactFlowProvider>
  );
}
