import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart } from '../components/charts/TrendChart';
import { TempFlow, type TempSenal } from '../components/scada/TempFlow';
import { KnobControl } from '../components/scada/KnobControl';
import { usePlcVirtualTemp, N_ALTO, N_BAJO } from '../components/scada/plcVirtualTemp';
import { CajaPlanta, chequeosPlanta, leerSim, moverLlave, usePlantaModo } from '../components/scada/plantaSimulada';
import { ModuloHeader, type EstadoCom, type Modo } from '../components/scada/ModuloHeader';
import { HistoricoModal } from '../components/scada/HistoricoModal';
import { ConfirmarOrden } from '../components/common/Emergente';
import { ageSeconds, formatAge, num, timeOnly } from '../utils/format';
import type { ControlOrden, TemperaturaSenales } from '../types';
import { enviarControlTemperatura, estadoControlTemperatura, listarOrdenesTemperatura, nombreControl } from '../services/control';

const ID = 'temp-mct09';
function real(s: TemperaturaSenales | null, key: string): number | null { const v=s?.valores?.[key]?.valor; if(typeof v==='number') return Number.isFinite(v)?v:null; if(typeof v==='boolean') return v?1:0; const n=typeof v==='string'?Number(v):NaN; return Number.isFinite(n)?n:null; }
function bit(s: TemperaturaSenales | null, key: string): boolean | null { const v=real(s,key); return v==null?null:v>=.5; }

/** El MCT-09 real no mide el nivel: solo tiene switches alto/bajo (T1 enfriador %M6/%M7, T2 principal %M4/%M5).
 *  Se DIBUJA un nivel aproximado: alto -> 92 %, bajo -> 10 %, ninguno -> 60 % (un poco sobre la mitad). */
function nivelPorSwitches(alto:boolean|null,bajoOk:boolean|null):number|null{if(alto==null||bajoOk==null)return null;return alto?92:!bajoOk?10:60;}
const noOk=(ok:boolean|null):boolean|null=>ok==null?null:!ok;

export function ModuleTempPage() {
  const { byId, historyFor, load, error, reload, now, link, temperaturaSenal } = usePlant();
  const eq=byId[ID]; const samples=useMemo(()=>historyFor(ID).slice(-300),[historyFor]);
  const [pid,setPid]=useState({kp:'',ti:'',td:''});
  const [modo,setModo]=useState<Modo>('real'), [historicoAbierto,setHistoricoAbierto]=useState(false);
  const [armado,setArmado]=useState(false), [mensaje,setMensaje]=useState('Comprobando control protegido…'), [ordenes,setOrdenes]=useState<ControlOrden[]>([]), [abierto,setAbierto]=useState(false), [sp,setSp]=useState(25), [spArrastre,setSpArrastre]=useState<number|null>(null), [usuario,setUsuario]=useState(nombreControl());
  // PLC virtual (solo SIMULADOR): recibe las llaves que el operador mueve en el mímico
  const [confirmar,setConfirmar]=useState<'Iniciar'|'Detener'|null>(null);
  const [valvSim,setValvSim]=useState<Record<string,boolean|null>>({}), [spSim,setSpSim]=useState(25);
  const plc=usePlcVirtualTemp(modo==='simulador',valvSim);
  const simulada=usePlantaModo()==='simulado';   // backend con MODO_PLANTA=simulado
  const [avisoLlave,setAvisoLlave]=useState<string|null>(null);
  const onLlave=useCallback((id:string,abierta:boolean)=>{setAvisoLlave(`${id}: ${abierta?'abriendo':'cerrando'}…`);void moverLlave(ID,id,abierta).then((e)=>setAvisoLlave(e?`${id}: ${e}`:null));},[]);
  const cargar=async()=>{ const [estado,lista]=await Promise.all([estadoControlTemperatura(),listarOrdenesTemperatura()]); const e=estado.datos?.datos; setArmado(estado.ok&&e?.realArmado===true); setUsuario(estado.datos?.usuario??nombreControl()); if(lista.ok&&lista.datos)setOrdenes(lista.datos); if(!estado.ok)setMensaje(`Control: ${estado.error??'sin respuesta'}`); else if(!e?.realArmado)setMensaje('Control físico bloqueado: modo REAL no armado'); else if(e.proceso.selector!=='PC')setMensaje('Control bloqueado: selector en HMI/local'); else if(!e.telemetria.fresca)setMensaje('Control bloqueado: telemetría vencida'); else setMensaje('Control REAL habilitado · M30 y MW100-MW103'); };
  useEffect(()=>{ void cargar(); const i=window.setInterval(()=>void cargar(),3000); return()=>window.clearInterval(i); },[]);
  if(load==='loading')return <LoadingBlock label="Cargando SCADA de temperatura…"/>;
  if(load==='error'||!eq)return <ErrorBlock message={error??'No se recibió el módulo de temperatura.'} onRetry={reload}/>;
  const edad=ageSeconds(now,eq.timestamp), edadSenal=temperaturaSenal?.ultimo?ageSeconds(now,temperaturaSenal.ultimo):Infinity;
  const online=temperaturaSenal?.mqtt===true&&temperaturaSenal.plc==='CONECTADO'&&edadSenal!=null&&edadSenal<=15;
  const pc=bit(temperaturaSenal,'estado/selector_remoto')===true, hmi=bit(temperaturaSenal,'estado/selector_local')===true;
  const temp=real(temperaturaSenal,'temperatura/principal_c')??eq.value, spReal=real(temperaturaSenal,'pid/setpoint_c'), setpoint=spArrastre??spReal??sp, puede=armado&&online&&pc&&!hmi;
  const senal:TempSenal={online,tempControl:online?temp:null,tempCooler:real(temperaturaSenal,'temperatura/enfriador_c'),nivelAprox:true,nivel1Pct:online?nivelPorSwitches(bit(temperaturaSenal,'nivel/enfriador_alto'),bit(temperaturaSenal,'nivel/enfriador_bajo_ok')):null,nivel2Pct:online?nivelPorSwitches(bit(temperaturaSenal,'nivel/principal_alto'),bit(temperaturaSenal,'nivel/principal_bajo_ok')):null,bomba:bit(temperaturaSenal,'estado/bomba_marcha'),caudal:real(temperaturaSenal,'caudal/l_min'),heaterPct:real(temperaturaSenal,'pid/salida_pct'),coolerOn:bit(temperaturaSenal,'estado/enfriador_on'),valvulas:{V1:bit(temperaturaSenal,'estado/v1'),V2:bit(temperaturaSenal,'estado/v2'),VF:bit(temperaturaSenal,'estado/v3'),V4:bit(temperaturaSenal,'estado/v4')},altoTE:bit(temperaturaSenal,'nivel/enfriador_alto'),bajoTE:noOk(bit(temperaturaSenal,'nivel/enfriador_bajo_ok')),altoTP:bit(temperaturaSenal,'nivel/principal_alto'),bajoTP:noOk(bit(temperaturaSenal,'nivel/principal_bajo_ok'))};
  // PLANTA SIMULADA: llaves y niveles de T1/T2 vienen del simulador Python
  const simT=leerSim(temperaturaSenal?.valores,['V1','V2','VF','V4']);
  if(simulada&&simT.hay){senal.valvulas=simT.valvulas;senal.nivel1Pct=simT.t1;senal.nivelAprox=false;senal.nivel2Pct=simT.t2;senal.altoTE=simT.t1Alto;senal.bajoTE=simT.t1Bajo;senal.altoTP=simT.t2Alto;senal.bajoTP=simT.t2Bajo;}
  const chequeosSim=chequeosPlanta(online,simT,{abiertas:[],cerradas:['V1','V2','V4','VF'],tanques:['t1','t2']});
  const bloqueoSim=simulada&&!chequeosSim.every(c=>c.ok);
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
  // Guarda de una vez los parámetros PID que se hayan escrito (cada uno se verifica con lectura del PLC)
  // Solo se envían los parámetros que el operador cambió respecto a lo que tiene el PLC
  const pidCambiados=()=>(['kp','ti','td'] as const).filter(k=>pid[k]!==''&&Number(pid[k])!==pidVal(k));
  const guardarPidTodos=async()=>{ for(const k of pidCambiados()) await guardarPid(k); setPid({kp:'',ti:'',td:''}); };
  const estadoCom:EstadoCom=online?'conectado':link==='reconnecting'||link==='connecting'?'reconectando':'sin-comunicacion';
  // SIMULADOR: solo cambia lo que se DIBUJA en el mímico; las órdenes quedan deshabilitadas.
  const sim=modo==='simulador';
  const plcOk=plc.conexion==='conectado';
  const senalSim:TempSenal={online:plcOk,tempControl:plcOk?plc.t2:null,tempCooler:plcOk?plc.t1:null,nivel1Pct:plc.n1,nivel2Pct:plc.n2,bomba:plcOk?plc.marcha:null,caudal:plcOk?plc.caudal:null,heaterPct:plcOk?plc.salida:null,coolerOn:plcOk?plc.marcha:null,valvulas:{},
    altoTE:plc.n1>=N_ALTO,bajoTE:plc.n1<=N_BAJO,altoTP:plc.n2>=N_ALTO,bajoTP:plc.n2<=N_BAJO};
  const seriesSim=[{id:'temp',label:'TEMPERATURA',color:'#e2412d',points:plc.historial.map(x=>({t:Date.parse(x.ts),v:x.value}))},...(plc.sp>0?[{id:'sp',label:'SETPOINT',color:'#ffd600',dashed:true,points:plc.historial.map(x=>({t:Date.parse(x.ts),v:plc.sp}))}]:[])];
  const salida=Math.max(0,Math.min(100,real(temperaturaSenal,'pid/salida_pct')??0));
  const pidVal=(k:'kp'|'ti'|'td')=>real(temperaturaSenal,`pid/${k}`);

  return <div className="lv-scada">
    <ModuloHeader id={eq.id} titulo="Módulo de control de temperatura" meta="Schneider Twido TWDLCAE40DRF · 192.168.114.10 · telemetría y control real protegido" estado={sim?(plcOk?'conectado':plc.conexion==='conectando'?'reconectando':'sin-comunicacion'):estadoCom} modo={modo} onModoChange={setModo}/>

    <div className="lv-main ca-layout">
      <section className="panel mimic-panel ca-flow tp-flow">
        <div className="panel-head"><div><h2>Diagrama mímico</h2></div></div>
        <TempFlow senal={sim?senalSim:senal} interactivo={sim} onValvulas={setValvSim} onLlave={!sim&&simulada?onLlave:undefined}/>
      </section>

      {/* columna derecha: tendencia + paneles de control */}
      <div className="ca-side">
        <section className="lv-trend">
          <div className="lv-trend-head">
            <b>Tendencia del proceso</b>
            <div className="ca-trend-right">
              <span>{sim?`${plc.historial.length} muestras · ${plcOk?'PLC virtual':'PLC virtual desconectado'}`:`${samples.length} muestras · ${online?(link==='connected'?'en vivo':link):'PLC sin datos'}`}</span>
              {sim?<span className="pill pill-warn">SIMULADOR</span>:<span className={`pill ${armado?'pill-err':'pill-warn'}`}>{armado?'REAL':'BLOQUEADO'}</span>}
            </div>
          </div>
          <div className="lv-chart"><TrendChart series={sim?seriesSim:series} unit="°C" size="tall" yTicks={[0,10,20,30,40,50,60]} timeTitle emptyText="Sin telemetría de temperatura · esperando el PLC Twido…"/></div>
          <div className="lv-chart-foot"><span>Última lectura</span><b>{sim?(plcOk?`PLC virtual · ${num(plc.t2,1)} °C`:'PLC virtual desconectado'):online?`${timeOnly(eq.timestamp)} · ${formatAge(edad)}`:'Sin comunicación · módulo apagado'}</b></div>
        </section>

        <div className="lv-controls">
          <section className="lv-control-card lv-options"><h3>Opciones</h3>
            <div className="co-top">
              <button type="button" className="co-ver" onClick={()=>{setAbierto(true);void cargar();}}>Órdenes <span className={ordenes.length?'co-cont':'co-cont vacio'}>{ordenes.length}</span></button>
              <button type="button" className="co-ver" onClick={()=>setHistoricoAbierto(true)}>Histórico</button>
            </div>
            <small>{usuario} · supervisor</small>
            <div className="lv-opt-btns">
              <button disabled={sim?!plcOk||plc.marcha:!puede||bloqueoSim} onClick={()=>{if(sim){void plc.iniciar();return;}setConfirmar('Iniciar');}}>Iniciar</button>
              <button disabled={sim?!plc.marcha:!armado||!online} onClick={()=>{if(sim){plc.detener();return;}setConfirmar('Detener');}}>Detener</button>
            </div>
            {sim&&<div className="plcv">
              <div className="plcv-head">
                <span className={`plcv-dot ${plc.conexion}`}/>
                <b>PLC virtual · Twido</b>
                {plc.conexion==='desconectado'
                  ?<button type="button" onClick={plc.conectar}>Conectar</button>
                  :<button type="button" disabled={plc.conexion==='conectando'} onClick={plc.desconectar}>{plc.conexion==='conectando'?'Conectando…':'Desconectar'}</button>}
              </div>
              <ul className="plcv-checks">{plc.chequeos.map(c=><li key={c.id} className={c.ok?'ok':''}>{c.ok?'✔':'✖'} {c.texto}</li>)}</ul>
              <small>{plc.marcha?`EN MARCHA · SP ${plc.sp.toFixed(1)} °C · T2 ${plc.t2.toFixed(1)} °C`:plc.listo?'Todo listo: puedes dar Iniciar':'Cumple los enclavamientos para poder iniciar'}</small>
            </div>}
            {!sim&&simulada&&<CajaPlanta chequeos={chequeosSim} aviso={avisoLlave}/>}
            <small>{sim?plc.mensaje:mensaje}</small>
          </section>

          <section className="lv-control-card lv-signals"><h3>Controlador</h3>
            <div className="ca-sig-table">
              <div><span>Origen de mando</span><strong>{pc?'PC / SCADA WEB':hmi?'HMI / LOCAL':'Sin dato'}</strong></div>
              <div><span>T principal</span><strong>{sim?(plcOk?`${num(plc.t2,2)} °C`:'Sin dato'):online&&temp!=null?`${num(temp,2)} °C`:'Sin dato'}</strong></div>
              <div><span>T enfriador</span><strong>{sim?(plcOk?`${num(plc.t1,2)} °C`:'Sin dato'):real(temperaturaSenal,'temperatura/enfriador_c')==null?'Sin dato':`${num(real(temperaturaSenal,'temperatura/enfriador_c')!,2)} °C`}</strong></div>
              <div><span>Señal control</span><strong>{sim?(plcOk?`${num(plc.salida,1)} %`:'Sin dato'):real(temperaturaSenal,'pid/salida_pct')==null?'Sin dato':`${num(real(temperaturaSenal,'pid/salida_pct')!,1)} %`}</strong></div>
            </div>
          </section>

          <div className="ca-pid-col">
            <section className="lv-control-card lv-pid ca-sp"><h3>Setpoint</h3>
              <div className="ca-command">{sim
                ?<KnobControl value={spSim} min={15} max={50} ticks={[15,20,25,30,35,40,45,50]} label="Setpoint °C" disabled={!plcOk} editable onChange={setSpSim} onCommit={(v)=>plc.cargarSetpoint(v)}/>
                :<KnobControl value={setpoint} min={15} max={50} ticks={[15,20,25,30,35,40,45,50]} label="Setpoint °C" disabled={!puede} editable onChange={(v)=>{setSp(v);setSpArrastre(v)}} onCommit={confirmarSp}/>}</div>
            </section>
            <section className="lv-control-card lv-pid"><h3>Control PID</h3>
              <div className="lv-pid-body">
                <dl>
                  {(['kp','ti','td'] as const).map(k=><div key={k}><dt>{k==='kp'?'Kp':k==='ti'?'Ti':'Td'}</dt><dd><input type="number" min="0" max="10000" step="1" value={pid[k]!==''?pid[k]:(pidVal(k)==null?'':String(pidVal(k)))} placeholder="—" onChange={e=>setPid({...pid,[k]:e.target.value})}/></dd></div>)}
                </dl>
                <button className="lv-pid-apply" disabled={sim||!puede||pidCambiados().length===0} title={!puede?'Requiere control armado, PLC en línea y selector en PC':pidCambiados().length===0?'Cambia Kp, Ti o Td para poder aplicar':'Envía los valores cambiados al PLC'} onClick={()=>void guardarPidTodos()}>Aplicar PID</button>
              </div>
            </section>
          </div>

          <section className="lv-control-card ca-pert"><h3>Salida PID</h3>
            <p className="ca-pert-sub">Resistencia / enfriamiento</p>
            <KnobControl value={sim?plc.salida:salida} max={100} ticks={[0,20,40,60,80,100]} label="% salida" disabled onChange={()=>{}}/>
            <small>Solo lectura</small>
          </section>
        </div>
      </div>
    </div>

    <HistoricoModal abierto={historicoAbierto} onClose={()=>setHistoricoAbierto(false)} id={eq.id} online={online} muestras={samples.length} ultima={timeOnly(eq.timestamp)} fuente="MQTT / UNS"/>
    {abierto&&<div className="co-modal" role="dialog" aria-modal="true" onClick={()=>setAbierto(false)}><div className="co-modal-caja" onClick={(e)=>e.stopPropagation()}><div className="co-modal-head"><b>Órdenes de control · temperatura-mct09</b><button onClick={()=>setAbierto(false)}>×</button></div><div className="co-modal-cuerpo">{ordenes.length===0?<p className="co-vacio">Sin órdenes todavía.</p>:<div className="co-list">{ordenes.map(o=><div className="co-item" key={o.id}><span>{o.tipo}{o.parametro?` ${o.parametro}`:''}{o.valor!=null?` = ${o.valor}${o.unidad?` ${o.unidad}`:''}`:''}</span><b className={o.estado==='Confirmado'?'ok':['Rechazado','Error','Timeout'].includes(o.estado)?'err':'wait'}>{o.estado}</b><small>{o.motivo??''} {timeOnly(o.actualizada??o.expedida)}</small></div>)}</div>}</div><div className="co-modal-pie">Modo REAL · %M30 y %MW100–%MW103 · cada orden exige lectura posterior coincidente</div></div></div>}
    <ConfirmarOrden abierto={confirmar!=null} accion={confirmar??'Iniciar'} equipo="temp-mct09" simulada={simulada}
      condiciones={[
        {etiqueta:'PLC Twido',valor:online?'CONECTADO':'DESCONECTADO',ok:online},
        {etiqueta:'Origen de mando',valor:pc?'PC / SCADA':hmi?'HMI / LOCAL':'sin dato',ok:pc},
        {etiqueta:'Temperatura T2',valor:online&&temp!=null?`${num(temp,1)} °C`:'sin dato'},
        {etiqueta:'Setpoint',valor:spReal!=null?`${num(spReal,1)} °C`:'sin dato',ok:confirmar==='Detener'?null:spReal!=null&&spReal>0},
        {etiqueta:'Control del backend',valor:armado?'ARMADO':'BLOQUEADO',ok:armado},
      ]}
      efecto={confirmar==='Detener'?'escribe %M30 = 0 y detiene el lazo (bomba, resistencia y enfriador)':'escribe %M30 = 1 y arranca el lazo (bomba, resistencia y enfriador)'}
      onCancelar={()=>setConfirmar(null)}
      onConfirmar={()=>{const a=confirmar;setConfirmar(null);if(a)void mandar(a);}}/>
  </div>;
}
