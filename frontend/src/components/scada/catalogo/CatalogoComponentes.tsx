import { Fragment, useState } from 'react';
import { tagStyle, type Place } from './valveTagCatalogo';
import { PumpTag } from '../PumpTag';
import { InstrumentTag, tagSize } from '../InstrumentTag';

/* ───────────── Índice lateral ───────────── */
const INDEX = [
  { id: 'cmp-sensores', label: 'Sensores', subs: [] as { id: string; label: string }[] },
  { id: 'cmp-llaves', label: 'Válvulas', subs: [] },
  { id: 'cmp-codos', label: 'Codos', subs: [] },
  { id: 'cmp-tees', label: 'Tees', subs: [] },
  { id: 'cmp-tapones', label: 'Tapones', subs: [] },
  { id: 'cmp-motores', label: 'Motores', subs: [] },
  { id: 'cmp-fuentes', label: 'Fuentes de agua', subs: [] },
];
const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
function ComponentIndex() {
  return <aside className="cmp-index"><span>ÍNDICE</span><ul>{INDEX.map((g) => <li key={g.id}>
    <button type="button" onClick={() => go(g.id)}>{g.label}</button>
    {g.subs.length > 0 && <ul>{g.subs.map((s) => <li key={s.id}><button type="button" onClick={() => go(s.id)}>{s.label}</button></li>)}</ul>}
  </li>)}</ul></aside>;
}

/* ───────────── Sensores ───────────── */
const SENSORS = [
  { label: 'ULTRASÓNICO', unit: 'cm', value: 38.2, module: 'Nivel · MCN-09' },
  { label: 'FLUJÓMETRO', unit: 'L/min', value: 18.5, module: 'Caudal · MCC-09' },
  { label: 'TRANSMISOR DE PRESIÓN', unit: 'PSI', value: 31.8, module: 'Presión · MCP-09' },
  { label: 'TERMOCUPLA', unit: '°C', value: 48.2, module: 'Temperatura · MCT-09' },
];
const SENSOR_SIZE = tagSize(SENSORS.map((s) => s.label), 12);
function SensorCard({ label, unit, value, module }: (typeof SENSORS)[number]) {
  const [online, setOnline] = useState(true);
  return <article className="keys-place-card"><div className="keys-scene cmp-scene">
    <svg width="110" height="64" viewBox="0 0 150 82" aria-hidden><rect x="55" y="6" width="40" height="22" rx="3" fill="#7b8794" stroke="#263746" strokeWidth="2"/><path d="M30 40q45-18 90 0v6H30z" fill="#3d4c5b" stroke="#263746" strokeWidth="2"/>{online && <g className="cmp-beam" fill="none" stroke="#4cc3f2" strokeWidth="3"><path d="M60 52q15 8 30 0"/><path d="M52 62q23 12 46 0"/><path d="M44 72q31 16 62 0"/></g>}</svg>
    <InstrumentTag label={label} size={SENSOR_SIZE} />
    <div className="cmp-reading"><strong>{online ? value.toFixed(1) : '—'}</strong><span>{online ? unit : 'SIN DATO'}</span></div>
    <button type="button" className="keys-motion__btn" onClick={() => setOnline((v) => !v)}>{online ? 'Desconectar' : 'Conectar'}</button>
  </div><b>{module}</b></article>;
}

/* ───────────── Motores ───────────── */
function MotorCard({ title, known = true }: { title: string; known?: boolean }) {
  const [on, setOn] = useState(false);
  return <article className="keys-place-card"><div className="keys-scene cmp-scene">
    <div className="cmp-pump">
    {/* rótulo centrado sobre el MOTOR (cuerpo azul), no sobre toda la bomba */}
    <div className="cmp-pump__tag"><PumpTag on={on} known={known} /></div>
    <svg width="200" height="92" viewBox="0 0 220 100" aria-hidden>
      <rect x="0" y="22" width="102" height="56" rx="8" fill="#2f55ff"/>
      {[14,26,38,50,62,74,86].map((x) => <line key={x} x1={x} y1="26" x2={x} y2="74" stroke="#0e1a66" strokeWidth="2"/>)}
      <rect x="102" y="32" width="14" height="36" fill="#7b8794"/>
      <rect x="116" y="18" width="80" height="64" rx="12" fill="#dce3e9" stroke="#768696" strokeWidth="2"/>
      <g className={on && known ? 'cmp-impeller on' : 'cmp-impeller'}><circle cx="156" cy="50" r="19" fill="#d5dce3" stroke="#8795a3" strokeWidth="2"/>{[0,60,120,180,240,300].map((a) => <line key={a} x1="156" y1="50" x2="156" y2="34" stroke="#5b6b7d" strokeWidth="3" transform={`rotate(${a} 156 50)`}/>)}</g>
    </svg>
    </div>
    {known && <button type="button" className="keys-motion__btn" onClick={() => setOn((v) => !v)}>{on ? 'Apagar' : 'Encender'}</button>}
  </div><b>{title}</b></article>;
}


function ValveGlyph({ open }: { open: boolean }) {
  return <svg width="70" height="40" viewBox="0 0 70 40" overflow="visible" aria-hidden>
    {/* tubo + bridas redondeadas en los extremos (mismo estilo que las TEE) */}
    {['pm-fit-outline', 'pm-fit-body'].map((cls) => <g key={cls} className={cls}>
      <rect x="2" y="15" width="66" height="10" />
      <rect x="0" y="11" width="5" height="18" rx="1.5" />
      <rect x="65" y="11" width="5" height="18" rx="1.5" />
    </g>)}
    <rect x="22" y="12" width="26" height="16" rx="3" className="v-flange" />
    <circle cx="35" cy="20" r="10" className={open ? 'v-body v-body--open' : 'v-body v-body--closed'} />
    <line x1="35" y1="10" x2="35" y2="6" className="v-stem" />
    <rect x="33" y="3" width="30" height="5" rx="2.5" className="v-lever" style={{ transformOrigin: '35px 5.5px', transform: `rotate(${open ? 0 : -90}deg)` }} />
  </svg>;
}

function ValveExample({ label, vertical, open, place, pipes = 'line', leverLeft = false, leverDown = false, onToggle }: { label: string; vertical: boolean; open: boolean; place: Place; pipes?: 'line' | 'top' | 'cross'; leverLeft?: boolean; leverDown?: boolean; onToggle?: () => void }) {
  return <div className={`keys-scene keys-scene--${pipes}`}><div className="keys-valve" style={{ width: vertical ? 40 : 70, height: vertical ? 70 : 40 }}>
    <div className="valve__hit" style={vertical ? { left: -15, top: 15, width: 70, height: 40, transform: leverLeft ? 'rotate(270deg)' : 'rotate(90deg)' } : { left: 0, top: 0, width: 70, height: 40, transform: leverLeft || leverDown ? `scale(${leverLeft ? -1 : 1}, ${leverDown ? -1 : 1})` : undefined }}><ValveGlyph open={open} /></div>
    {onToggle && <button type="button" className="keys-body-hit" aria-label={open ? 'Cerrar válvula' : 'Abrir válvula'} title={open ? 'Cerrar' : 'Abrir'} onClick={onToggle} style={vertical ? { left: 20, top: 35 } : { left: 35, top: 20 }} />}
    <span className="valve__tag" style={tagStyle(vertical, place, open, leverLeft, label, leverDown)}>{label}</span>
  </div></div>;
}

/** 1.1.1 · Movimiento: la misma válvula de «1 · Arriba» abriéndose y cerrándose. */
/* Rotación en pasos de 90°: cambia orientación de la válvula y lado de la palanca. */
const ROTATIONS = [
  { vertical: true, leverLeft: false, leverDown: false, name: 'Vertical · palanca derecha' },
  { vertical: false, leverLeft: true, leverDown: true, name: 'Horizontal · palanca abajo' },
  { vertical: true, leverLeft: true, leverDown: false, name: 'Vertical · palanca izquierda' },
  { vertical: false, leverLeft: false, leverDown: false, name: 'Horizontal · palanca arriba' },
];

function MotionCard() {
  const [open, setOpen] = useState(false);
  const [rot, setRot] = useState(0);
  const r = ROTATIONS[rot];
  const toggle = () => setOpen((v) => !v);
  return <article className="keys-place-card keys-motion-card">
    <div className="keys-motion">
      <ValveExample key={rot} label="V1" vertical={r.vertical} leverLeft={r.leverLeft} leverDown={r.leverDown} open={open} place="top" pipes="line" onToggle={toggle} />
      <span className="keys-motion__rot">{rot * 90}° · {r.name}</span>
      <span className={open ? 'keys-motion__state keys-motion__state--open' : 'keys-motion__state'}>{open ? 'ABIERTA' : 'CERRADA'}</span>
      <div className="keys-motion__actions">
        <button type="button" onClick={toggle}>{open ? 'Cerrar' : 'Abrir'}</button>
        <button type="button" onClick={() => setRot((n) => (n + 1) % ROTATIONS.length)} title="Rotar 90°">↻ Rotar</button>
      </div>
    </div>
    <b>Válvula</b>
  </article>;
}


/* ───────────── Fuentes de abastecimiento de agua (4 salidas) ───────────── */
type Lado = 't' | 'b' | 'l' | 'r';
const LADOS: { lado: Lado; nombre: string }[] = [
  { lado: 't', nombre: 'Salida superior' },
  { lado: 'b', nombre: 'Salida inferior' },
  { lado: 'r', nombre: 'Salida derecha' },
  { lado: 'l', nombre: 'Salida izquierda' },
];
function FuenteCard({ lado, nombre }: { lado: Lado; nombre: string }) {
  const [activa, setActiva] = useState(true);
  return <article className="keys-place-card"><div className="keys-scene cmp-scene">
    <div className="cat-supply">
      <svg width="170" height="100" viewBox="-14 -14 228 146" overflow="visible" aria-hidden>
        <rect x="25" y="24" width="150" height="68" rx="8" className="cat-supply__body" />
        <path d="M31 57q18-7 36 0t36 0t36 0t30 0v29H31z" className={activa ? 'cat-supply__water on' : 'cat-supply__water'} />
        {lado === 't' && <><rect x="84" y="4" width="32" height="22" rx="3" className="cat-supply__neck" /><path d="M72 4h56M100 4V-10" className="cat-supply__line" /></>}
        {lado === 'b' && <><rect x="84" y="90" width="32" height="22" rx="3" className="cat-supply__neck" /><path d="M72 112h56M100 112v14" className="cat-supply__line" /></>}
        {lado === 'l' && <><rect x="3" y="42" width="24" height="32" rx="3" className="cat-supply__neck" /><path d="M3 36v44M3 58H-12" className="cat-supply__line" /></>}
        {lado === 'r' && <><rect x="173" y="42" width="24" height="32" rx="3" className="cat-supply__neck" /><path d="M197 36v44M197 58h15" className="cat-supply__line" /></>}
      </svg>
      <span className="cat-supply__tag">ABASTECIMIENTO DE AGUA</span>
    </div>
    <button type="button" className="keys-motion__btn" onClick={() => setActiva((v) => !v)}>{activa ? 'Cortar agua' : 'Dar agua'}</button>
  </div><b>{nombre}</b></article>;
}


/* ───────────── Codos y Tees (rotables en pasos de 90°) ───────────── */
const NOMBRE_ROT = ['0°', '90°', '180°', '270°'];
const SALIDAS: Record<'codo' | 'tee' | 'tapon', string[]> = {
  tapon: ['entrada por la izquierda', 'entrada por arriba', 'entrada por la derecha', 'entrada por abajo'],
  codo: ['izquierda + abajo', 'arriba + izquierda', 'derecha + arriba', 'abajo + derecha'],
  tee: ['izquierda + derecha + abajo', 'arriba + abajo + izquierda', 'izquierda + derecha + arriba', 'arriba + abajo + derecha'],
};
function FittingGlyph({ tipo }: { tipo: 'codo' | 'tee' | 'tapon' }) {
  if (tipo === 'tapon') {
    /* tramo de tubo que llega por la izquierda y termina en un tapón (como tras V3/V4) */
    return <svg width="100" height="100" viewBox="0 0 100 100" overflow="visible" aria-hidden>
      {['pm-fit-outline', 'pm-fit-body'].map((cls) => <g key={cls} className={cls}>
        <rect x="2" y="45" width="58" height="10" /><rect x="0" y="41" width="5" height="18" rx="1.5" />
        <rect x="58" y="38" width="12" height="24" rx="3" />
      </g>)}
    </svg>;
  }
  /* tramos de tubo desde el centro (50,50) hacia las salidas, con bridas en las puntas */
  return <svg width="100" height="100" viewBox="0 0 100 100" overflow="visible" aria-hidden>
    {['pm-fit-outline', 'pm-fit-body'].map((cls) => <g key={cls} className={cls}>
      {/* salida izquierda */}
      <rect x="2" y="45" width="53" height="10" /><rect x="0" y="41" width="5" height="18" rx="1.5" />
      {/* salida abajo */}
      <rect x="45" y="45" width="10" height="53" /><rect x="41" y="95" width="18" height="5" rx="1.5" />
      {tipo === 'tee' && <>{/* salida derecha */}<rect x="45" y="45" width="53" height="10" /><rect x="95" y="41" width="5" height="18" rx="1.5" /></>}
      <rect x="40" y="40" width="20" height="20" rx="4" />
    </g>)}
  </svg>;
}
function FittingCard({ tipo }: { tipo: 'codo' | 'tee' | 'tapon' }) {
  const [rot, setRot] = useState(0);
  return <article className="keys-place-card keys-motion-card">
    <div className="keys-scene cmp-scene">
      <div style={{ transform: `rotate(${rot * 90}deg)`, transition: 'transform .3s ease' }}><FittingGlyph tipo={tipo} /></div>
      <span className="keys-motion__rot">{NOMBRE_ROT[rot]} · salidas: {SALIDAS[tipo][rot]}</span>
      <div className="keys-motion__actions">
        <button type="button" onClick={() => setRot((n) => (n + 1) % 4)} title="Rotar 90°">↻ Rotar</button>
      </div>
    </div>
    <b>{tipo === 'codo' ? 'Codo 90°' : tipo === 'tee' ? 'Tee' : 'Tapón'}</b>
  </article>;
}

export function KeysModule() {
  return <section className="keys-module process-mimic cmp-layout"><div className="cmp-main"><div className="keys-heading"><div><span>CATÁLOGO DE COMPONENTES</span><h2>Componentes</h2></div><p>Sensores, válvulas y motores usados en los 4 mímicos.</p></div>
    <h2 className="cmp-group" id="cmp-sensores">Sensores</h2>
    <div className="keys-grid keys-grid--places">{SENSORS.map((x) => <SensorCard key={x.label} {...x} />)}</div>
    <h2 className="cmp-group" id="cmp-llaves">Válvulas</h2>
    <div className="keys-grid keys-grid--places"><MotionCard /></div>
    <div className="keys-notes"><b>Orden:</b><span>Arriba → abajo → al lado de la palanca, centrado con ella.</span><b>Centrado:</b><span>Siempre respecto a la palanca azul; si tapa algo, pasa al siguiente lado.</span></div>
    <h2 className="cmp-group" id="cmp-codos">Codos</h2>
    <div className="keys-grid keys-grid--places"><FittingCard tipo="codo" /></div>
    <h2 className="cmp-group" id="cmp-tees">Tees</h2>
    <div className="keys-grid keys-grid--places"><FittingCard tipo="tee" /></div>
    <h2 className="cmp-group" id="cmp-tapones">Tapones</h2>
    <div className="keys-grid keys-grid--places"><FittingCard tipo="tapon" /></div>
  <h2 className="cmp-group" id="cmp-motores">Motores</h2>
    <div className="keys-grid keys-grid--places"><MotorCard title="Bomba" /></div>
    <h2 className="cmp-group" id="cmp-fuentes">Fuentes de abastecimiento de agua</h2>
    <div className="keys-grid keys-grid--places">{LADOS.map((x) => <FuenteCard key={x.lado} {...x} />)}</div>
  </div><ComponentIndex /></section>;
}
