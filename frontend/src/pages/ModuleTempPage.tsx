import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart } from '../components/charts/TrendChart';
import { TempFlow, type TempSenal } from '../components/scada/TempFlow';
import { KnobControl } from '../components/scada/KnobControl';
import { ageSeconds, formatAge, num, timeOnly } from '../utils/format';
import type { ControlOrden, TemperaturaSenales } from '../types';
import { enviarControlTemperatura, estadoControlTemperatura, listarOrdenesTemperatura, tokenControl } from '../services/control';

const ID = 'temp-mct09';
function real(s: TemperaturaSenales | null, key: string): number | null { const v=s?.valores?.[key]?.valor; if(typeof v==='number') return Number.isFinite(v)?v:null; if(typeof v==='boolean') return v?1:0; const n=typeof v==='string'?Number(v):NaN; return Number.isFinite(n)?n:null; }
function bit(s: TemperaturaSenales | null, key: string): boolean | null { const v=real(s,key); return v==null?null:v>=.5; }

export function ModuleTempPage() {
  const { byId, historyFor, load, error, reload, now, link, temperaturaSenal } = usePlant();
  const eq=byId[ID]; const samples=useMemo(()=>historyFor(ID).slice(-300),[historyFor]);
  const [pid,setPid]=useState({kp:'',ti:'',td:''});
  const [armado,setArmado]=useState(false), [mensaje,setMensaje]=useState('Comprobando control protegido…'), [ordenes,setOrdenes]=useState<ControlOrden[]>([]), [abierto,setAbierto]=useState(false), [sp,setSp]=useState(25), [spArrastre,setSpArrastre]=useState<number|null>(null), [usuario,setUsuario]=useState(tokenControl());
  const cargar=async()=>{ const [estado,lista]=await Promise.all([estadoControlTemperatura(),listarOrdenesTemperatura()]); const e=estado.datos?.datos; setArmado(estado.ok&&e?.realArmado===true); setUsuario(estado.datos?.usuario??tokenControl()); if(lista.ok&&lista.datos)setOrdenes(lista.datos); if(!estado.ok)setMensaje(`Control: ${estado.error??'sin respuesta'}`); else if(!e?.realArmado)setMensaje('Control físico bloqueado: modo REAL no armado'); else if(e.proceso.selector!=='PC')setMensaje('Control bloqueado: selector en HMI/local'); else if(!e.telemetria.fresca)setMensaje('Control bloqueado: telemetría vencida'); else setMensaje('Control REAL habilitado · M30 y MW100-MW103'); };
  useEffect(()=>{ void cargar(); const i=window.setInterval(()=>void cargar(),3000); return()=>window.clearInterval(i); },[]);
  if(load==='loading')return <LoadingBlock label="Cargando SCADA de temperatura…"/>;
  if(load==='error'||!eq)return <ErrorBlock message={error??'No se recibió el módulo de temperatura.'} onRetry={reload}/>;
  const edad=ageSeconds(now,eq.timestamp), edadSenal=temperaturaSenal?.ultimo?ageSeconds(now,temperaturaSenal.ultimo):Infinity;
  const online=temperaturaSenal?.mqtt===true&&temperaturaSenal.plc==='CONECTADO'&&edadSenal!=null&&edadSenal<=15;
  const pc=bit(temperaturaSenal,'estado/selector_remoto')===true, hmi=bit(temperaturaSenal,'estado/selector_local')===true;
  const temp=real(temperaturaSenal,'temperatura/principal_c')??eq.value, spReal=real(temperaturaSenal,'pid/setpoint_c'), setpoint=spArrastre??spReal??sp, puede=armado&&online&&pc&&!hmi;
  const senal:TempSenal={online,tempControl:online?temp:null,tempCooler:real(temperaturaSenal,'temperatura/enfriador_c'),nivel1Pct:real(temperaturaSenal,'nivel/principal_pct'),nivel2Pct:real(temperaturaSenal,'nivel/enfriador_pct'),bomba:bit(temperaturaSenal,'estado/bomba_marcha'),caudal:real(temperaturaSenal,'caudal/l_min'),heaterPct:real(temperaturaSenal,'pid/salida_pct'),coolerOn:bit(temperaturaSenal,'estado/enfriador_on'),valvulas:{V1:bit(temperaturaSenal,'estado/v1'),V2:bit(temperaturaSenal,'estado/v2'),V3:bit(temperaturaSenal,'estado/v3'),V4:bit(temperaturaSenal,'estado/v4')},altoTE:bit(temperaturaSenal,'falla/nivel_enfriador'),bajoTE:null,altoTP:bit(temperaturaSenal,'falla/nivel_principal'),bajoTP:null};
  const series=[{id:'temp',label:'TEMPERATURA',color:'#e2412d',points:samples.map(x=>({t:Date.parse(x.ts),v:x.value}))},...(spReal==null?[]:[{id:'sp',label:'SETPOINT',color:'#ffd600',dashed:true,points:samples.map(x=>({t:Date.parse(x.ts),v:spReal}))}])];
  const mandar=async(tipo:'Iniciar'|'Detener'|'Setpoint',valor?:number)=>{setMensaje(`Enviando ${tipo}…`);const r=await enviarControlTemperatura({tipo,valor,unidad:tipo==='Setpoint'?'C':undefined,comentario:'Orden desde SCADA de temperatura'});setMensaje(r.ok?`${tipo}: enviada; esperando lectura posterior`:`${tipo}: ${r.error??'rechazado'}`);window.setTimeout(()=>void cargar(),700);};
  // La perilla sigue al dedo mientras se arrastra y al soltar envía el SP sin pedir
  // confirmación (igual que nivel y presión). Mantiene el valor elegido hasta que el
  // PLC confirma la lectura; si la orden falla vuelve a mostrar la lectura real.
  const confirmarSp=(v:number)=>{setSp(v)
    if(!puede||v===spReal){setSpArrastre(null);return}
    setSpArrastre(v)
    void mandar('Setpoint',v).finally(()=>window.setTimeout(()=>setSpArrastre(null),2500))
  }

  const guardarPid=async(clave:'kp'|'ti'|'td')=>{
    const valor=Number(pid[clave]);
    if(!Number.isInteger(valor)||valor<0||valor>10000){setMensaje(`${clave.toUpperCase()}: usa un entero entre 0 y 10000`);return;}
    const r=await enviarControlTemperatura({tipo:'ParametroPid',parametro:clave,valor,comentario:`PID ${clave.toUpperCase()} desde SCADA de temperatura`});
    setMensaje(r.ok?`${clave.toUpperCase()}: enviada; esperando lectura posterior`:`${clave.toUpperCase()}: ${r.error??'rechazado'}`);
    window.setTimeout(()=>void cargar(),700);
  };
  return <div className="lv-scada">
    <div className="lv-title"><div><span>{eq.id}</span><h2>Módulo de control de temperatura</h2></div><div className={`lv-live ${online?'on':''}`}><i/>{online?'PLC conectado':'Sin comunicación'}</div></div>
    <div className="lv-main"><section className="panel mimic-panel ca-flow tp-flow"><div className="panel-head"><div><h2>Diagrama mímico</h2><span className="panel-sub">Twido · {eq.ip} · telemetría y control real protegido</span></div><span className={`pill ${online?'pill-ok pill-live':'pill-err'}`}><i/>{online?'PLC conectado':'Sin comunicación'}</span></div><TempFlow senal={senal}/></section><section className="lv-trend"><div className="lv-trend-head"><div><b>Tendencia del proceso</b><small>Temperatura y consigna en °C</small></div><span>{samples.length} muestras · {online?(link==='connected'?'en vivo':link):'PLC sin datos'}</span></div><div className="lv-chart"><TrendChart series={series} unit="°C" size="tall" yTicks={[0,10,20,30,40,50,60]} timeTitle emptyText="Sin telemetría de temperatura · esperando el PLC Twido…"/></div><div className="lv-chart-foot"><span>Última lectura</span><b>{online?`${timeOnly(eq.timestamp)} · ${formatAge(edad)}`:'Sin comunicación · módulo apagado'}</b></div></section></div>
    <div className="lv-controls">
      <section className="lv-control-card lv-options"><h3>Opciones</h3><div className="co-top"><span className={`pill ${armado?'pill-err':'pill-warn'}`}>{armado?'REAL':'BLOQUEADO'}</span><button className="co-ver" onClick={()=>{setAbierto(true);void cargar();}}>Órdenes <span className={ordenes.length?'co-cont':'co-cont vacio'}>{ordenes.length}</span></button></div><small>{usuario} · supervisor</small><div className="lv-opt-btns"><button disabled={!puede} onClick={()=>{if(window.confirm('Iniciar el lazo de temperatura desde PC?'))void mandar('Iniciar');}}>Iniciar</button><button disabled={!armado||!online} onClick={()=>{if(window.confirm('Detener el lazo de temperatura?'))void mandar('Detener');}}>Detener</button></div><small>{mensaje}</small></section>
      <section className="lv-control-card lv-signals"><h3>Controlador</h3><div><span>Origen de mando</span><b>{pc?'PC / SCADA WEB':hmi?'HMI / LOCAL':'Sin selección'}</b></div><div><span>T principal</span><strong>{online&&temp!=null?`${num(temp,2)} °C`:'Sin dato'}</strong></div><div><span>T enfriador</span><strong>{real(temperaturaSenal,'temperatura/enfriador_c')==null?'Sin dato':`${num(real(temperaturaSenal,'temperatura/enfriador_c')!,2)} °C`}</strong></div><div><span>Señal control</span><strong>{real(temperaturaSenal,'pid/salida_pct')==null?'Sin dato':`${num(real(temperaturaSenal,'pid/salida_pct')!,1)} %`}</strong></div></section>
      <section className="lv-control-card lv-pid"><h3>PID y setpoint</h3><div className="lv-pid-body"><dl><div><dt>Kp</dt><dd>{real(temperaturaSenal,'pid/kp')==null?'—':num(real(temperaturaSenal,'pid/kp')!,2)}</dd></div><div><dt>Ti</dt><dd>{real(temperaturaSenal,'pid/ti')==null?'—':num(real(temperaturaSenal,'pid/ti')!,2)}</dd></div><div><dt>Td</dt><dd>{real(temperaturaSenal,'pid/td')==null?'—':num(real(temperaturaSenal,'pid/td')!,2)}</dd></div></dl><KnobControl value={setpoint} min={15} max={50} ticks={[15,20,25,30,35,40,45,50]} label="Setpoint °C" disabled={!puede} onChange={(v)=>{setSp(v);setSpArrastre(v)}} onCommit={confirmarSp}/></div><small>La perilla envía SP al PLC; Kp, Ti y Td se ajustan abajo.</small></section>
      <section className="lv-control-card lv-temp-pid-edit"><h3>Ajuste PID del Twido</h3><p>Kp, Ti y Td se guardan por separado y se comprueban con lectura del PLC.</p>{(['kp','ti','td'] as const).map(clave=><label key={clave} style={{display:'flex',alignItems:'center',gap:8,marginBottom:8}}><b style={{width:35}}>{clave.toUpperCase()}</b><input type="number" min="0" max="10000" step="1" value={pid[clave]} placeholder={String(real(temperaturaSenal,`pid/${clave}`)??'Sin dato')} onChange={e=>setPid({...pid,[clave]:e.target.value})} style={{width:100}}/><button disabled={!puede||pid[clave]===''} onClick={()=>void guardarPid(clave)}>Guardar</button></label>)}</section>
      <section className="lv-control-card ca-pert"><h3>Salida PID</h3><p className="ca-pert-sub">Resistencia / enfriamiento</p><KnobControl value={Math.max(0,Math.min(100,real(temperaturaSenal,'pid/salida_pct')??0))} max={100} ticks={[0,20,40,60,80,100]} label="% salida" disabled onChange={()=>{}}/><small>Solo lectura</small></section>
      <section className="lv-control-card lv-record"><h3>Histórico</h3><div className="lv-rec-icon">●</div><div><span>Tasa</span><b>1 segundo</b></div><div><span>Muestras</span><b>{samples.length}</b></div><div><span>Última lectura</span><b className="nodata">{online?timeOnly(eq.timestamp):'Sin datos'}</b></div><div><span>Fuente</span><b>MQTT / UNS</b></div></section>
    </div>
    {abierto&&<div className="co-modal" role="dialog" aria-modal="true" onClick={()=>setAbierto(false)}><div className="co-modal-caja" onClick={(e)=>e.stopPropagation()}><div className="co-modal-head"><b>Órdenes de control · temperatura-mct09</b><button onClick={()=>setAbierto(false)}>×</button></div><div className="co-modal-cuerpo">{ordenes.length===0?<p className="co-vacio">Sin órdenes todavía.</p>:<div className="co-list">{ordenes.map(o=><div className="co-item" key={o.id}><span>{o.tipo}{o.parametro?` ${o.parametro}`:''}{o.valor!=null?` = ${o.valor}${o.unidad?` ${o.unidad}`:''}`:''}</span><b className={o.estado==='Confirmado'?'ok':['Rechazado','Error','Timeout'].includes(o.estado)?'err':'wait'}>{o.estado}</b><small>{o.motivo??''} {timeOnly(o.actualizada??o.expedida)}</small></div>)}</div>}</div><div className="co-modal-pie">Modo REAL · %M30 y %MW100–%MW103 · cada orden exige lectura posterior coincidente</div></div></div>}
  </div>;
}
