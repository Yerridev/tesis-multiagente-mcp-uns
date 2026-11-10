import { observarEncuadre, useMedidasEstables } from './encuadre';
import { CatalogoBoton } from './catalogo/CatalogoBoton';
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Background, BackgroundVariant, Controls, Handle, Position, ReactFlow, ReactFlowProvider, getSmoothStepPath, getStraightPath, useEdges, useNodeId, useReactFlow, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import { WaterSupplyNode } from './WaterSupplyNode';
import { CatalogEndNode, CatalogJunctionNode, CatalogValveNode } from './CatalogParts';
import { PumpTag } from './PumpTag';

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
  /** true en planta REAL: el nivel dibujado sale de los switches (no hay sensor de nivel) */
  nivelAprox?: boolean;
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

const Sw = ({ on, alarma }: { on: boolean | null; alarma?: boolean }) => <i className={on ? (alarma ? 'led led--alarm' : 'led led--on') : 'led'} />;

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

/* Serpentín de T1 (coordenadas locales del tanque 210×245).
   Entra por x=125, baja en zigzag detrás de la lectura y sale por x=175. */
const COIL_PATH = 'M125 -4 V90 H26 V127 H152 V164 H26 V201 H175 V-4';
const COIL_HALO = 'M125 0 V90 H26 V127 H152 V164 H26 V201 H175 V0';

/** Etiqueta del nivel: % real (simulador) o estado de los switches (planta real). */
function textoNivel(pct: number, aprox: boolean): string {
  if (!aprox) return `${pct.toFixed(0)} %`;
  return pct >= 85 ? 'NIVEL ALTO' : pct <= 15 ? 'NIVEL BAJO' : 'NIVEL NORMAL';
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
        <g className={coil ? 'coil coil--cold' : 'coil'}>
          <path d={COIL_HALO} className="coil-halo" />
          <path d={COIL_PATH} className="coil-wall" />
          <path d={COIL_PATH} className="coil-body" />
          <path d={COIL_PATH} className="coil-shine" />
        </g>
        <rect x="-10" y="52" width="14" height="16" rx="3" className={d.altoTE === true ? 'level-switch-orange on' : 'level-switch-orange'} />
        <rect x="-10" y="182" width="14" height="16" rx="3" className={d.bajoTE === true ? 'level-switch-orange on' : 'level-switch-orange'} />
      </SteelTank>
      <div className="tank__readout"><strong>{temp == null ? '—' : temp.toFixed(0)}</strong><span>{temp == null ? 'sin dato' : '°C'}</span></div>
      <span className="tag" style={{ left: '50%', top: 8, transform: 'translateX(-50%)', textAlign: 'center' }}>T1 · ENFRIAMIENTO · {pct == null ? 'SIN DATO' : textoNivel(pct, d.aprox === true)}</span>
      <span className="tag level-tag" style={{ right: 224, top: 60 }}>NIVEL ALTO <Sw on={d.altoTE === true} alarma /></span>
      <span className="tag level-tag" style={{ right: 224, top: 190 }}>NIVEL BAJO <Sw on={d.bajoTE === true} alarma /></span>
      <Port id="in" position={Position.Bottom} style={{ left: 30 }} />
      <Port id="ovf" position={Position.Bottom} style={{ left: 130 }} />
      <Port id="retV2" position={Position.Bottom} style={{ left: 175 }} />
      <Port id="v1" position={Position.Top} style={{ left: 45 }} />
      <Port id="coilU" position={Position.Top} style={{ left: 125 }} />
      <Port id="coilD" position={Position.Top} style={{ left: 175 }} />
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
        : dir === 'right'
          ? { left: 100, top: 12, minWidth: 96, whiteSpace: 'nowrap', minHeight: 42, display: 'grid', placeItems: 'center', textAlign: 'center', lineHeight: 1.25, padding: '6px 8px' }
          : { right: 100, top: 12, minWidth: 96, whiteSpace: 'nowrap', minHeight: 42, display: 'grid', placeItems: 'center', textAlign: 'center', lineHeight: 1.25, padding: '6px 8px' };
  return (
    <div className="valve nodrag nopan" title="Solo lectura · sin órdenes al equipo" style={{ width: vertical ? 40 : 70, height: vertical ? 70 : 40 }}>
      <div style={{ position: 'absolute', left: vertical ? -15 : 0, top: vertical ? 15 : 0, width: 70, height: 40, transform: `rotate(${rot}deg)` }}>
        <svg width="70" height="40" viewBox="0 0 70 40" overflow="visible" role="img" aria-label={`${label}: ${known ? `${t.toFixed(1)} grados Celsius` : 'sin dato'}`}>
          <rect x="0" y="15" width="70" height="10" className="v-pipe" />
          <rect x="24" y="11" width="22" height="18" rx="3" className="v-flange" />
          <rect x="31" y="-6" width="8" height="18" className="ts-stem" />
          <rect x="28" y="3" width="14" height="5" rx="1" className="ts-nut" />
          {/* válvula del sensor: verde abierta · rojo cerrada (simulador); en REAL muestra el color de la temperatura */}
          {typeof d.abierta === 'boolean'
            ? <circle cx="35" cy="20" r="5.5" fill={d.abierta ? '#22c55e' : '#ef4444'} stroke="#0b141c" strokeWidth="1.2" style={{ transition: 'fill .3s', filter: `drop-shadow(0 0 3px ${d.abierta ? '#22c55e' : '#ef4444'})` }} />
            : <circle cx="35" cy="20" r="3.5" fill={col} stroke="#0b141c" strokeWidth="1" style={{ transition: 'fill .4s' }} />}
          <rect x="17" y={headY} width="36" height={-5 - headY} rx="5" className="ts-head" />
          <rect x="21" y={sy} width="28" height={sh} rx="2" className="ts-screen" />
          <text x="35" y={sc} textAnchor="middle" dominantBaseline="central" transform={`rotate(${-rot} 35 ${sc})`} className="ts-text" style={{ fill: disp, fontSize: em }}>
            {shown}
          </text>
          <circle cx="35" cy="-11" r="2.5" className="ts-led" />
        </svg>
      </div>
      <span className="tag" style={tag}>
        {label === 'TEMPERATURA SALIDA'
          ? <>TEMPERATURA<br />SALIDA</>
          : label === 'TEMPERATURA ENTRADA'
            ? <>TEMPERATURA<br />ENTRADA</>
            : label}
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

/* Resistencia tubular en horquilla, reducida 20 % y elevada. */
const HEATER_PATH = 'M0 160.4 H117 A9.6 9.6 0 0 1 117 179.6 H0';

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
        <g className={heating ? 'heater heater--on' : 'heater'} transform="translate(0,-8)">
          <path d={HEATER_PATH} className="heater-halo" />
          <path d={HEATER_PATH} className="heater-wall" />
          <path d={HEATER_PATH} className="heater-body" />
          <path d={HEATER_PATH} className="heater-shine" />
          <rect x="-4.8" y="150.8" width="4.8" height="38.4" rx="1.6" className="heater-flange" />
          <rect x="-9.6" y="164.4" width="4.8" height="11.2" className="heater-neck" />
          <rect x="-22.4" y="158.8" width="12.8" height="22.4" rx="2.4" className="heater-head" />
          <circle cx="-16" cy="165.2" r="1.9" className="heater-stud" />
          <circle cx="-16" cy="174.8" r="1.9" className="heater-stud" />
        </g>
        <rect x="206" y="42" width="14" height="16" rx="3" className={d.altoTP === true ? 'level-switch-orange on' : 'level-switch-orange'} />
        <rect x="206" y="167" width="14" height="16" rx="3" className={d.bajoTP === true ? 'level-switch-orange on' : 'level-switch-orange'} />
      </SteelTank>
      <div className="tank__readout" style={{ top: 88 }}>   {/* centrado entre la etiqueta T2 y la resistencia */}<strong>{temp == null ? '—' : temp.toFixed(0)}</strong><span>{temp == null ? 'sin dato' : '°C'}</span></div>
      <span className="tag" style={{ left: '50%', top: 8, transform: 'translateX(-50%)', textAlign: 'center' }}>T2 · PRINCIPAL · {pct == null ? 'SIN DATO' : textoNivel(pct, d.aprox === true)}</span>
      <span className="tag level-tag level-tag--right" style={{ left: 224, top: 50 }}><Sw on={d.altoTP === true} alarma /> NIVEL ALTO</span>
      <span className="tag level-tag level-tag--right" style={{ left: 224, top: 175 }}><Sw on={d.bajoTP === true} alarma /> NIVEL BAJO</span>
      <span className="tag" style={{ left: 12, top: 190 }}>RESISTENCIA {heater == null ? 'SIN DATO' : `${heater.toFixed(0)} %`}</span>
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

const nodeTypes = {
  junction: CatalogJunctionNode,
  end: CatalogEndNode,
  valve: CatalogValveNode,
  pump: PumpNode,
  tankT1: TankT1Node,
  tankT2: TankT2Node,
  chiller: ChillerNode,
  supply: WaterSupplyNode,
  tempSensor: TempSensorNode,
};

/* ───────────── Tubería (borde ReactFlow) ───────────── */
function PipeEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  const edgeData = data as Data | undefined;
  const routeUp = edgeData?.routeUp === true;
  const [straightPath] = getStraightPath({ sourceX, sourceY, targetX, targetY });
  const path = routeUp
      ? `M ${sourceX},${sourceY} L ${sourceX},${targetY} L ${targetX},${targetY}`
      : straightPath;
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
  { id: 'pump', type: 'pump', position: { x: 285, y: 1040 }, data: {}, ...fixed },
  { id: 't1', type: 'tankT1', position: { x: 425, y: 270 }, data: {}, ...fixed },
  { id: 't2', type: 'tankT2', position: { x: 525, y: 690 }, data: {}, ...fixed },
  { id: 'chiller', type: 'chiller', position: { x: 780, y: 430 }, data: {}, ...fixed },
  { id: 'TS', type: 'tempSensor', position: { x: 630, y: 925 }, data: { label: 'TEMPERATURA SALIDA', dir: 'left', src: 'control' }, ...fixed },
  { id: 'TSE', type: 'tempSensor', position: { x: 580, y: 565 }, data: { label: 'TEMPERATURA ENTRADA', dir: 'right', src: 'cooler' }, ...fixed },
  /* Posición nominal: V1, V2, V4 y VF cerradas (V2 se abre a mano para bajar agua de T1 a T2) */
  valve('V1', 670, 165, 'h', false), valve('V2', 555, 600, 'v', false, 'left'),
  /* VF (llave de la fuente) queda en la subida del abastecimiento, separada de su boca superior. */
  valve('VF', 920, 885, 'v', false),
  valve('V4', 700, 975, 'v', false),   /* descarga de T2: la tubería termina en la llave (bota el agua) */   /* 0° · vertical · palanca derecha */
  junction('JV', 575, 165), junction('JIN', 470, 165), junction('JS', 650, 1090),
  { id: 'SUPPLY', type: 'supply', position: { x: 820, y: 927 }, data: { side: 't' }, ...fixed },
];

const ed = (id: string, source: string, sh: string, target: string, th: string, type: 'pipe' | 'coolant' = 'pipe', extra: Data = {}): Edge => ({
  id, source, sourceHandle: sh, target, targetHandle: th, type, data: { active: false, ...extra },
});

const EDGES: Edge[] = [
  ed('d1', 'pump', 'discharge', 't1', 'in'),
  ed('r1', 't1', 'retV2', 'TSE', 't'), ed('r2', 'TSE', 'b', 't2', 'inA'),
  ed('ov', 't1', 'ovf', 'V2', 't'), ed('ov2', 'V2', 'b', 't2', 'inB'),
  ed('s1', 't2', 'out', 'TS', 't'), ed('s1b', 'TS', 'b', 'JS', 't'), ed('s2', 'JS', 'l', 'pump', 'suction'),
  ed('dr', 't2', 'inS', 'V4', 't'),
  ed('x0', 'SUPPLY', 't', 'VF', 'b'),
  ed('x1', 'VF', 't', 'V1', 'r', 'pipe', { routeUp: true }),
  ed('f2', 'V1', 'l', 'JV', 'r'), ed('f3a', 'JV', 'l', 'JIN', 'r'), ed('f3b', 'JIN', 'b', 't1', 'v1'),
  /* Refrigerante: sube por la derecha y pasa por encima de T1 sin cruzarse. */
  ed('c1', 'chiller', 'outU', 't1', 'coilU', 'coolant', { turnX: 745, topY: 238 }),
  ed('c2', 'chiller', 'outD', 't1', 'coilD', 'coolant', { turnX: 690, topY: 258 }),
];

const TEMP_TAG_PLAN = {
  V1: { open: 'top', closed: 'right', unknown: 'right' },
  V2: { open: 'left', closed: 'top', unknown: 'top' },
  VF: { open: 'top', closed: 'top', unknown: 'top' },
  V4: { open: 'top', closed: 'top', unknown: 'top' },
} as const;

/* ───────────── Tubería de refrigerante (enfriador ↔ serpentín del T1) ───────────── */
function CoolantEdge({ sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  /* Del enfriador sale horizontal, sube, pasa sobre T1 y baja hasta su tapa. */
  const d = data as Data | undefined;
  const turnX = typeof d?.turnX === 'number' ? d.turnX : sourceX - 40;
  const topY = typeof d?.topY === 'number' ? d.topY : targetY - 30;
  const path = `M ${sourceX},${sourceY} H ${turnX} V ${topY} H ${targetX} V ${targetY}`;
  return (
    <g>
      <path d={path} className="coolant-wall" />
      <path d={path} className="coolant-bore" />
      <path d={path} className="coolant-shine" />
    </g>
  );
}

const edgeTypes = { pipe: PipeEdge, coolant: CoolantEdge };

/* ───────────── Lienzo con re-encaje automático ───────────── */
type MapaValv = Record<string, boolean | null>;
function Flow({ senal, interactivo = false, onValvulas, onLlave }: { senal: TempSenal; interactivo?: boolean; onValvulas?: (v: MapaValv) => void; onLlave?: (id: string, abierta: boolean) => void }) {
  const rf = useReactFlow();
  const ref = useRef<HTMLDivElement>(null);
  /* SIMULADOR: las llaves se abren/cierran con clic (solo visual, nunca órdenes al PLC). En REAL son fijas. */
  const [manual, setManual] = useState<Record<string, boolean>>({});
  const nominal = (id: string) => { const nom = (BASE_NODES.find((x) => x.id === id)?.data as Data | undefined)?.nominal; return typeof nom === 'boolean' ? nom : null; };
  const abierta = (id: string): boolean | null => {
    if (interactivo) return id in manual ? manual[id] : nominal(id);
    return senal.valvulas[id] ?? nominal(id);
  };
  const alternar = (id: string) => {
    if (interactivo) setManual((m) => ({ ...m, [id]: !(abierta(id) === true) }));
    else onLlave?.(id, !(abierta(id) === true));   // PLANTA SIMULADA: la mueve el simulador Python
  };
  const clicable = interactivo || !!onLlave;
  const IDS = ['V1', 'V2', 'VF', 'V4'];
  const firma = IDS.map((v) => String(abierta(v))).join(',');
  useEffect(() => {
    onValvulas?.(Object.fromEntries(IDS.map((v) => [v, abierta(v)])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firma]);
  const circula = senal.online && senal.bomba === true;   // en marcha: válvulas-sensor abiertas

  const nodes = useMemo<Node[]>(() => {
    return BASE_NODES.map((n) => {
      const data: Data = { ...n.data };
      if (n.type === 'pump') data.on = senal.bomba;
      if (n.type === 'tempSensor') {
        data.temp = (n.data as Data).src === 'cooler' ? senal.tempCooler : senal.tempControl;
        if (clicable) data.abierta = circula;
      }
      if (n.type === 'tankT1') {
        data.nivelPct = senal.nivel1Pct;
        data.aprox = senal.nivelAprox;
        data.temp = senal.tempCooler;
        data.coolant = senal.online && senal.coolerOn === true;
        data.altoTE = senal.altoTE;
        data.bajoTE = senal.bajoTE;
      }
      if (n.type === 'tankT2') {
        data.nivelPct = senal.nivel2Pct;
        data.aprox = senal.nivelAprox;
        data.temp = senal.tempControl;
        data.heaterPct = senal.heaterPct;
        data.altoTP = senal.altoTP;
        data.bajoTP = senal.bajoTP;
      }
      if (n.type === 'chiller') data.on = senal.coolerOn;
      if (n.type === 'valve') {
        data.open = abierta(String(n.id));
        if (clicable) data.onToggle = () => alternar(String(n.id));
        data.tagPlan = TEMP_TAG_PLAN[String(n.id) as keyof typeof TEMP_TAG_PLAN];
      }
      if (n.type === 'supply') data.active = (interactivo || senal.online) && abierta('VF') === true;
      if (n.type === 'end') data.active = circula;
      return { ...n, data };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [senal, manual, interactivo, onLlave]);

  /* El agua avanza hasta la primera llave cerrada: fuente → VF → V1 → T1; T1 → V2 → T2;
     y la recirculación (bomba y válvulas-sensor) solo en marcha. */
  const edges = useMemo<Edge[]>(() => {
    const hayAgua = interactivo || senal.online;
    const v3 = abierta('VF') === true,   /* VF: llave de la fuente */ v1 = abierta('V1') === true, v2 = abierta('V2') === true, v4 = abierta('V4') === true;
    return EDGES.map((e) => ({
      ...e,
      data: {
        ...e.data,
        active: e.id === 'x0' || e.id === 'x1'
          ? hayAgua && v3
          : ['f2', 'f3a', 'f3b'].includes(e.id)
            ? hayAgua && v3 && v1
            : e.id === 'dr'
              ? hayAgua && v4 && (senal.nivel2Pct ?? (interactivo ? 0 : 100)) > 0.5
            : ['ov', 'ov2'].includes(e.id)
              ? hayAgua && v2 && (senal.nivel1Pct ?? (interactivo ? 0 : 100)) > 0.5
              : circula,
      },
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [senal, manual, interactivo, onLlave]);

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

export function TempFlow({ senal, interactivo = false, onValvulas, onLlave }: { senal: TempSenal; interactivo?: boolean; onValvulas?: (v: MapaValv) => void; onLlave?: (id: string, abierta: boolean) => void }) {
  return (
    <ReactFlowProvider>
      <Flow key={interactivo ? 'sim' : 'real'} senal={senal} interactivo={interactivo} onValvulas={onValvulas} onLlave={onLlave} />
    </ReactFlowProvider>
  );
}
