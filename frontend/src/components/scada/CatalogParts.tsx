import { Handle, Position, useEdges, useNodeId, type NodeProps } from '@xyflow/react';
import type { CSSProperties } from 'react';

type Data = Record<string, unknown>;
type Box = [number, number, number, number];

function Port({ id, position, style }: { id: string; position: Position; style?: CSSProperties }) {
  return <><Handle id={id} type="source" position={position} style={style} isConnectable={false}/><Handle id={id} type="target" position={position} style={style} isConnectable={false}/></>;
}

const ARM: Record<string, { body: Box; flange: Box }> = {
  l:{body:[2,17,20,10],flange:[0,13,5,18]}, r:{body:[22,17,20,10],flange:[39,13,5,18]},
  t:{body:[17,2,10,20],flange:[13,0,18,5]}, b:{body:[17,22,10,20],flange:[13,39,18,5]},
};

export function CatalogJunctionNode() {
  const id=useNodeId(), edges=useEdges();
  const arms=[...new Set(edges.filter(e=>e.source===id||e.target===id).map(e=>e.source===id?e.sourceHandle:e.targetHandle).filter((h):h is string=>!!h))];
  return <div className="junction">{arms.length>=2&&<svg width="44" height="44" viewBox="0 0 44 44" className="ca-fitting" aria-hidden>
    {['ca-fit-outline','ca-fit-body'].map(cls=><g className={cls} key={cls}><rect x="17" y="17" width="10" height="10" rx="3"/>{arms.map(a=>ARM[a]&&<g key={a}><rect x={ARM[a].body[0]} y={ARM[a].body[1]} width={ARM[a].body[2]} height={ARM[a].body[3]}/><rect x={ARM[a].flange[0]} y={ARM[a].flange[1]} width={ARM[a].flange[2]} height={ARM[a].flange[3]} rx="1.5"/></g>)}</g>)}
  </svg>}<Port id="t" position={Position.Top}/><Port id="b" position={Position.Bottom}/><Port id="l" position={Position.Left}/><Port id="r" position={Position.Right}/></div>;
}

export function CatalogEndNode({data}:NodeProps) {
  const d=data as Data, side=String(d.side) as 'l'|'r'|'t';
  return <div className={`pipe-end pipe-end--${side}`}><div className="pipe-end__flange"/>{d.active===true&&<span className="drip"/>}<Port id={side} position={side==='l'?Position.Left:side==='t'?Position.Top:Position.Right}/></div>;
}

function ValveGlyph({open}:{open:boolean|null}) {
  const cls=open===true?'v-body v-body--open':open===false?'v-body v-body--closed':'v-body v-body--unknown';
  return <svg width="70" height="40" viewBox="0 0 70 40" overflow="visible" aria-hidden><rect x="0" y="15" width="70" height="10" className="v-pipe"/><rect x="22" y="12" width="26" height="16" rx="3" className="v-flange"/><circle cx="35" cy="20" r="10" className={cls}/><line x1="35" y1="10" x2="35" y2="6" className="v-stem"/><rect x="33" y="3" width="30" height="5" rx="2.5" className="v-lever" style={{transformOrigin:'35px 5.5px',transform:`rotate(${open?0:-90}deg)`}}/></svg>;
}

export function CatalogValveNode({data}:NodeProps) {
  const d=data as Data, orientation=String(d.orientation) as 'h'|'v', open=(d.open as boolean|null)??null, vertical=orientation==='v', leverLeft=d.lever==='left';
  return <div className="valve nodrag nopan" title="Solo lectura · sin órdenes al PLC" style={{width:vertical?40:70,height:vertical?70:40}}><div className="valve__hit" style={vertical?{left:-15,top:15,width:70,height:40,transform:leverLeft?'rotate(270deg)':'rotate(90deg)'}:{left:0,top:0,width:70,height:40}}><ValveGlyph open={open}/></div><span className="valve__tag" style={vertical?(leverLeft?{right:46,top:8}:{left:46,top:26}):{left:0,top:-18,width:70}}>{String(d.label??'')}</span>{vertical?<><Port id="t" position={Position.Top}/><Port id="b" position={Position.Bottom}/></>:<><Port id="l" position={Position.Left}/><Port id="r" position={Position.Right}/></>}</div>;
}

export function CatalogPumpNode({data}:NodeProps) {
  const d=data as Data,on=d.on===true,known=d.on!==null&&d.on!==undefined,mirror=d.mirror===true,air=d.air===true;
  return <div className="pump nodrag nopan" title="Solo lectura · sin órdenes al PLC" style={{width:220,height:100}}><div className="pump__hit"><svg width="220" height="100" viewBox="0 0 220 100" aria-hidden style={mirror?{transform:'scaleX(-1)'}:undefined}><defs><linearGradient id={`cat-motor-${mirror?'m':'n'}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3b6bff"/><stop offset="1" stopColor="#1b2fa8"/></linearGradient><linearGradient id={`cat-case-${mirror?'m':'n'}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#f4f6f8"/><stop offset="1" stopColor="#aab4be"/></linearGradient></defs><rect x="165" width="10" height="20" className="v-pipe"/><rect x="194" y="45" width="26" height="10" className="v-pipe"/><rect width="86" height="56" x="0" y="22" rx="8" fill={`url(#cat-motor-${mirror?'m':'n'})`}/>{[12,24,36,48,60,72].map(x=><line key={x} x1={x} y1="26" x2={x} y2="74" stroke="#0e1a66" strokeWidth="2" opacity=".55"/>)}<rect x="86" y="32" width="12" height="36" className="pump__coupling"/>{air?<><rect x="98" y="28" width="24" height="44" rx="5" className="pump__brass"/><rect x="122" y="32" width="12" height="36" className="pump__coupling"/></>:<rect x="98" y="32" width="36" height="36" className="pump__coupling"/>}<rect x="134" y="18" width="80" height="64" rx="12" fill={`url(#cat-case-${mirror?'m':'n'})`}/><g className={on?'impeller impeller--on':'impeller'}><circle cx="174" cy="50" r="19" fill="#d5dce3" stroke="#8795a3" strokeWidth="2"/>{[0,60,120,180,240,300].map(a=><line key={a} x1="174" y1="50" x2="174" y2="34" stroke="#5b6b7d" strokeWidth="3" strokeLinecap="round" transform={`rotate(${a} 174 50)`}/>)}</g><circle cx="12" cy="12" r="5" className={on&&known?'led led--on':'led'}/></svg></div><span className="tag" style={{left:mirror?135:5,top:-24}}>BOMBA · {!known?'SIN DATO':on?'MARCHA':'PARO'}</span><Port id="discharge" position={Position.Top} style={{left:mirror?50:170}}/><Port id="suction" position={mirror?Position.Left:Position.Right}/>{air&&<Port id="air" position={Position.Top} style={{left:110,top:28}}/>}</div>;
}
