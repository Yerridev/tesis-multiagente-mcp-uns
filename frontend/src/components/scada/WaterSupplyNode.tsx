import { Handle, Position, type NodeProps } from '@xyflow/react';

type Side='l'|'r'|'t'|'b';
type Data=Record<string,unknown>;

export function WaterSupplyNode({data}:NodeProps){
  const d=data as Data,side=String(d.side??'t') as Side,active=d.active===true;
  const position=side==='l'?Position.Left:side==='r'?Position.Right:side==='b'?Position.Bottom:Position.Top;
  /* La boca debe quedar a la altura de la brida dibujada (y=58 en el lienzo), no al centro del nodo. */
  const style=side==='l'?{top:58}:side==='r'?{top:58}:side==='b'?{bottom:35}:undefined;
  return <div className="industrial-supply" title="Fuente externa representada; sin medición en el PLC">
    <Handle id={side} type="source" position={position} style={style} isConnectable={false}/><Handle id={side} type="target" position={position} style={style} isConnectable={false}/>
    <svg width="200" height="118" viewBox="-10 -10 220 138" overflow="visible" aria-hidden>
      <rect x="25" y="24" width="150" height="68" rx="8" className="industrial-supply__body"/>
      <path d="M31 57q18-7 36 0t36 0t36 0t30 0v29H31z" className={active?'industrial-supply__water active':'industrial-supply__water'}/>
      {side==='t'&&<><rect x="84" y="4" width="32" height="22" rx="3" className="industrial-supply__neck"/><path d="M72 4h56M100 4V-8" className="industrial-supply__line"/></>}
      {side==='b'&&<><rect x="84" y="90" width="32" height="22" rx="3" className="industrial-supply__neck"/><path d="M72 112h56M100 112v12" className="industrial-supply__line"/></>}
      {side==='l'&&<><rect x="3" y="42" width="24" height="32" rx="3" className="industrial-supply__neck"/><path d="M3 36v44M3 58H-9" className="industrial-supply__line"/></>}
      {side==='r'&&<><rect x="173" y="42" width="24" height="32" rx="3" className="industrial-supply__neck"/><path d="M197 36v44M197 58h12" className="industrial-supply__line"/></>}
    </svg><b>ABASTECIMIENTO DE AGUA</b><span>FUENTE EXTERNA · SALIDA {side==='l'?'IZQUIERDA':side==='r'?'DERECHA':side==='b'?'INFERIOR':'SUPERIOR'}</span>
  </div>;
}
