import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart } from '../components/charts/TrendChart';
import { CaudalFlow, type CaudalSenal, type EstadoMimico } from '../components/scada/CaudalFlow';
import { usePlcVirtualCaudal } from '../components/scada/plcVirtualCaudal';
import { KnobControl } from '../components/scada/KnobControl';
import { CajaPlanta, chequeosPlanta, leerSim, moverLlave, usePlantaModo } from '../components/scada/plantaSimulada';
import { ModuloHeader, type EstadoCom, type Modo } from '../components/scada/ModuloHeader';
import { ConfirmarOrden } from '../components/common/Emergente';
import { ageSeconds, formatAge, num, timeOnly } from '../utils/format';
import type { CaudalSenales, ControlOrden } from '../types';
import { enviarControlCaudal, estadoControlCaudal, listarOrdenesCaudal, tokenControl } from '../services/control';

const ID = 'caudal-mcc09';

/** useState que recuerda el valor en localStorage (sobrevive a recargar la página). */
function useRecordado(clave: string, inicial: string): [string, (v: string) => void] {
  const k = `mcp.caudal.${clave}`;
  const [v, setV] = useState<string>(() => {
    try { return localStorage.getItem(k) ?? inicial; } catch { return inicial; }
  });
  const guardar = useCallback((nuevo: string) => {
    setV(nuevo);
    try { localStorage.setItem(k, nuevo); } catch { /* sin almacenamiento: solo en memoria */ }
  }, [k]);
  return [v, guardar];
}

function real(s: CaudalSenales | null, key: string): number | null {
  const v = s?.valores?.[key]?.valor;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'boolean') return v ? 1 : 0;
  const n = typeof v === 'string' ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}

function estado(s: CaudalSenales | null, key: string): boolean | null {
  const v = real(s, key);
  return v == null ? null : v >= 0.5;
}

export function ModuleCaudalPage() {
  const { byId, historyFor, load, error, reload, now, link, caudalSenal } = usePlant();
  const eq = byId[ID];
  const samples = useMemo(() => historyFor(ID).slice(-300), [historyFor]);
  const [armado, setArmado] = useState(false);
  const [mensaje, setMensaje] = useState('Comprobando control…');
  // Los mandos arrancan con lo último que dejó el operador (localStorage) y, en cuanto llega
  // telemetría, toman el valor REAL del PLC (lo que de verdad está cargado).
  const [sp, setSp] = useRecordado('sp', '0');
  const [valvula, setValvula] = useRecordado('valvula', '100');
  const [kc, setKc] = useRecordado('kc', '1');
  const [ti, setTi] = useRecordado('ti', '0.01');
  const [td, setTd] = useRecordado('td', '0');
  const [sincronizado, setSincronizado] = useState(false);
  const [ordenes, setOrdenes] = useState<ControlOrden[]>([]);
  const [ordenesAbiertas, setOrdenesAbiertas] = useState(false);
  const [historicoAbierto, setHistoricoAbierto] = useState(false);
  const [confirmarInicio, setConfirmarInicio] = useState(false);
  const [confirmarDetencion, setConfirmarDetencion] = useState(false);
  const [modo, setModo] = useState<Modo>('real');
  const [usuario, setUsuario] = useState(tokenControl());
  // PLC virtual (solo modo SIMULADOR): recibe el estado de llaves/tanque del mímico
  const [estadoMimico, setEstadoMimico] = useState<EstadoMimico>({ valvulas: {}, nivelPct: null, nivelBajo: null });
  const plc = usePlcVirtualCaudal(modo === 'simulador', estadoMimico, Number(valvula) || 0);
  const simulada = usePlantaModo() === 'simulado';   // backend con MODO_PLANTA=simulado
  const [avisoLlave, setAvisoLlave] = useState<string | null>(null);
  // Una sola vez por visita: copiar a los mandos lo que tiene cargado el PLC
  useEffect(() => {
    if (sincronizado || !caudalSenal?.valores) return;
    const spPlc = real(caudalSenal, 'caudal/setpoint');
    const valPlc = real(caudalSenal, 'actuadores/valvula_pct');
    const kcPlc = real(caudalSenal, 'pid/kc'), tiPlc = real(caudalSenal, 'pid/ti'), tdPlc = real(caudalSenal, 'pid/td');
    if (spPlc == null && valPlc == null && kcPlc == null) return;
    const txt = (v: number) => String(Math.round(v * 1000) / 1000);
    if (spPlc != null) setSp(txt(spPlc));
    if (valPlc != null) setValvula(String(Math.round(valPlc)));
    if (kcPlc != null && kcPlc > 0) setKc(txt(kcPlc));
    if (tiPlc != null && tiPlc > 0) setTi(txt(tiPlc));
    if (tdPlc != null) setTd(txt(tdPlc));
    setSincronizado(true);
  }, [caudalSenal, sincronizado, setSp, setValvula, setKc, setTi, setTd]);

  const onLlave = useCallback((id: string, abierta: boolean) => {
    setAvisoLlave(`${id}: ${abierta ? 'abriendo' : 'cerrando'}…`);
    void moverLlave('caudal-mcc09', id, abierta).then((e) => setAvisoLlave(e ? `${id}: ${e}` : null));
  }, []);

  const cargarOrdenes = async () => {
    const r = await listarOrdenesCaudal();
    if (r.ok && r.datos) setOrdenes(r.datos);
  };

  useEffect(() => {
    void estadoControlCaudal().then((r) => {
      const ok = r.ok && r.datos?.datos.realArmado === true;
      setArmado(ok);
      setUsuario(r.datos?.usuario ?? tokenControl());
      setMensaje(ok ? 'Control REAL habilitado' : 'Control físico bloqueado hasta la puesta en marcha');
    });
    void cargarOrdenes();
  }, []);

  const mandar = async (tipo: string, valor?: number, parametro?: string, unidad?: string) => {
    setMensaje(`Enviando ${tipo}…`);
    const r = await enviarControlCaudal({ tipo, valor, parametro, unidad, comentario: 'Orden desde SCADA de caudal' });
    setMensaje(r.ok ? `${tipo}: enviada; esperando lectura posterior` : `${tipo}: ${r.error ?? 'rechazado'}`);
    window.setTimeout(() => void cargarOrdenes(), 500);
  };

  const aplicarPid = async () => {
    const valores = [
      ['kc', Number(kc)],
      ['ti', Number(ti)],
      ['td', Number(td)],
    ] as const;
    if (valores.some(([, valor]) => !Number.isFinite(valor))) {
      setMensaje('PID: completa Kc, Ti y Td con valores válidos');
      return;
    }
    setMensaje('Enviando parámetros PID…');
    for (const [parametro, valor] of valores) {
      const r = await enviarControlCaudal({
        tipo: 'ParametroPid',
        valor,
        parametro,
        comentario: 'Ajuste PID desde SCADA de caudal',
      });
      if (!r.ok) {
        setMensaje(`PID ${parametro}: ${r.error ?? 'rechazado'}`);
        await cargarOrdenes();
        return;
      }
    }
    setMensaje('PID enviado; esperando tres lecturas posteriores');
    window.setTimeout(() => void cargarOrdenes(), 500);
  };

  if (load === 'loading') return <LoadingBlock label="Cargando Scada Caudal…" />;
  if (load === 'error' || !eq) return <ErrorBlock message={error ?? 'No se recibió el módulo de caudal.'} onRetry={reload} />;

  const age = ageSeconds(now, eq.timestamp);
  const signalAge = caudalSenal?.ultimo ? ageSeconds(now, caudalSenal.ultimo) : Number.POSITIVE_INFINITY;
  const online = caudalSenal?.mqtt === true && caudalSenal.plc === 'CONECTADO' && (signalAge ?? Number.POSITIVE_INFINITY) <= 15;
  const liveCaudal = real(caudalSenal, 'caudal/pv_pid') ?? real(caudalSenal, 'caudal/caudalimetro');
  const setpoint = real(caudalSenal, 'caudal/setpoint_pid') ?? real(caudalSenal, 'caudal/setpoint');
  const series = [
    { id: 'caudal', label: 'CAUDAL', color: '#1e88e5', points: samples.map((s) => ({ t: Date.parse(s.ts), v: s.value })) },
    ...(setpoint == null
      ? []
      : [{ id: 'sp', label: 'SETPOINT', color: '#ffd600', dashed: true, points: samples.map((s) => ({ t: Date.parse(s.ts), v: setpoint })) }]),
  ];

  // Solo existe señal real de caudal (búfer /api/history). El resto de señales no tiene fuente: «Sin dato».
  const senal: CaudalSenal = {
    online,
    caudal: online ? liveCaudal : null,
    presion: null,
    nivelPct: null,
    bomba: estado(caudalSenal, 'estado/sistema_funcionando'),
    valvulaPct: real(caudalSenal, 'actuadores/valvula_pct'),
    valvulas: { V1: null, V2: null, V3: null, V4: null, V5: null, V6: null, V7: null },
    nivelAlto: estado(caudalSenal, 'estado/nivel_alto'),
    nivelBajo: estado(caudalSenal, 'estado/nivel_bajo'),
  };
  // PLANTA SIMULADA: llaves y T1 vienen del simulador Python
  const simC = leerSim(caudalSenal?.valores, ['V1', 'V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'VF']);
  if (simulada && simC.hay) {
    senal.valvulas = simC.valvulas;
    senal.nivelPct = simC.t1;
    senal.nivelAlto = simC.t1Alto;
    senal.nivelBajo = simC.t1Bajo;
  }
  const chequeosSim = chequeosPlanta(online, simC, { abiertas: ['V5', 'V2'], cerradas: ['V1', 'V3', 'V4', 'V6', 'V7'], tanques: ['t1'] });   // T1 sin nivel alto ni nivel bajo
  const bloqueoSim = simulada && !chequeosSim.every((c) => c.ok);

  // Estado de comunicación para la cabecera
  const estadoCom: EstadoCom = online ? 'conectado' : link === 'reconnecting' || link === 'connecting' ? 'reconectando' : 'sin-comunicacion';
  // SIMULADOR: solo cambia lo que se DIBUJA en el mímico; nunca habilita órdenes al PLC.
  const sim = modo === 'simulador';
  const plcOk = plc.conexion === 'conectado';
  const senalSim: CaudalSenal = {
    online: plcOk,
    caudal: plcOk ? plc.caudal : null,
    presion: plcOk ? (plc.marcha ? plc.caudal * 0.32 : 0) : null,
    nivelPct: null,          // el tanque lo simula el mímico (se llena con VF+V1, drena con V7)
    bomba: plcOk ? plc.marcha : null,
    valvulaPct: plcOk ? Number(valvula) || 0 : null,
    valvulas: { V1: null, V2: null, V3: null, V4: null, V5: null, V6: null, V7: null },   // las mueve el operador en el mímico
    nivelAlto: null, nivelBajo: null,
  };
  const seriesSim = [
    { id: 'caudal', label: 'CAUDAL', color: '#1e88e5', points: plc.historial.map((x) => ({ t: Date.parse(x.ts), v: x.value })) },
    ...(plc.sp > 0 ? [{ id: 'sp', label: 'SETPOINT', color: '#ffd600', dashed: true, points: plc.historial.map((x) => ({ t: Date.parse(x.ts), v: plc.sp })) }] : []),
  ];

  return (
    <div className="lv-scada">
      <ModuloHeader
        id={eq.id}
        titulo="Módulo de control de caudal"
        meta="Siemens S7-200 · 192.168.114.7 · telemetría y control real protegido"
        estado={sim ? (plcOk ? 'conectado' : plc.conexion === 'conectando' ? 'reconectando' : 'sin-comunicacion') : estadoCom}
        modo={modo}
        onModoChange={setModo}
      />

      <div className="lv-main ca-layout">
        <section className="panel mimic-panel ca-flow">
          <div className="panel-head">
            <div>
              <h2>Diagrama mímico</h2>
            </div>
          </div>
          <CaudalFlow senal={sim ? senalSim : senal} onEstado={setEstadoMimico} interactivo={sim} onLlave={!sim && simulada ? onLlave : undefined} />
        </section>

        {/* columna derecha: tendencia + paneles de control */}
        <div className="ca-side">
        <section className="lv-trend">
          <div className="lv-trend-head">
            <b>Tendencia del proceso</b>
            <div className="ca-trend-right">
              <span>
                {sim ? `${plc.historial.length} muestras · ${plcOk ? 'PLC virtual' : 'PLC virtual desconectado'}` : `${samples.length} muestras · ${online ? (link === 'connected' ? 'en vivo' : link) : 'PLC sin datos'}`}
              </span>
              {sim ? <span className="pill pill-warn">SIMULADOR</span> : <span className={`pill ${armado ? 'pill-err' : 'pill-warn'}`}>{armado ? 'REAL' : 'BLOQUEADO'}</span>}
            </div>
          </div>
          <div className="lv-chart">
            <TrendChart
              series={sim ? seriesSim : series}
              unit="L/min"
              size="tall"
              yTicks={[0, 20, 40, 60, 80]}
              timeTitle
              emptyText="Sin telemetría de caudal · esperando el PLC Siemens S7-200…"
            />
          </div>
          <div className="lv-chart-foot">
            <span>Última lectura</span>
            <b>{online ? `${timeOnly(eq.timestamp)} · ${formatAge(age)}` : 'Sin comunicación · módulo apagado'}</b>
          </div>
        </section>

      <div className="lv-controls">
        <section className="lv-control-card lv-options">
          <h3>Opciones</h3>
          <div className="co-top">
            <button type="button" className="co-ver" onClick={() => { setOrdenesAbiertas(true); void cargarOrdenes(); }}>
              Órdenes <span className={ordenes.length ? 'co-cont' : 'co-cont vacio'}>{ordenes.length}</span>
            </button>
            <button type="button" className="co-ver" onClick={() => setHistoricoAbierto(true)}>Histórico</button>
          </div>
          <small>{usuario} · supervisor</small>
          <div className="lv-opt-btns">
            <button disabled={sim ? !plcOk || plc.marcha : !armado || !online || bloqueoSim} onClick={() => (sim ? void plc.iniciar() : setConfirmarInicio(true))}>Iniciar</button>
            <button disabled={sim ? !plc.marcha : !armado || !online} onClick={() => (sim ? plc.detener() : setConfirmarDetencion(true))}>Detener</button>
          </div>
          {sim && (
            <div className="plcv">
              <div className="plcv-head">
                <span className={`plcv-dot ${plc.conexion}`} />
                <b>PLC virtual · S7-200</b>
                {plc.conexion === 'desconectado'
                  ? <button type="button" onClick={plc.conectar}>Conectar</button>
                  : <button type="button" disabled={plc.conexion === 'conectando'} onClick={plc.desconectar}>{plc.conexion === 'conectando' ? 'Conectando…' : 'Desconectar'}</button>}
              </div>
              <ul className="plcv-checks">
                {plc.chequeos.map((c) => <li key={c.id} className={c.ok ? 'ok' : ''}>{c.ok ? '✔' : '✖'} {c.texto}</li>)}
              </ul>
              <small>{plc.marcha ? `EN MARCHA · SP ${plc.sp.toFixed(1)} L/min · FT ${plc.caudal.toFixed(1)} L/min` : plc.listo ? 'Todo listo: puedes dar Iniciar' : 'Cumple los enclavamientos para poder iniciar'}</small>
            </div>
          )}
          {!sim && simulada && <CajaPlanta chequeos={chequeosSim} aviso={avisoLlave} />}
          <small>{sim ? plc.mensaje : mensaje}</small>
        </section>

        <section className="lv-control-card lv-signals">
          <h3>Controlador</h3>
          <div className="ca-sig-table">
          <div>
            <span>Controlador</span>
            <strong>{estado(caudalSenal, 'estado/selector_remoto') ? 'REMOTO' : estado(caudalSenal, 'estado/selector_local') ? 'LOCAL' : 'Sin dato'}</strong>
          </div>
          <div>
            <span>Señal caudal</span>
            <strong>{sim ? (plcOk ? `${num(plc.caudal, 1)} L/min` : 'Sin dato') : online && liveCaudal != null ? `${num(liveCaudal, 1)} L/min` : 'Sin dato'}</strong>
          </div>
          <div>
            <span>Señal control</span>
            <strong>{sim ? (plcOk ? `${num(plc.variador, 1)} %` : 'Sin dato') : real(caudalSenal, 'actuadores/variador_pct') == null ? 'Sin dato' : `${num(real(caudalSenal, 'actuadores/variador_pct')!, 1)} %`}</strong>
          </div>
          </div>
        </section>

        <div className="ca-pid-col">
        <section className="lv-control-card lv-pid">
          <h3>Control PID</h3>
          <div className="lv-pid-body">
            <dl>
              <div>
                <dt>Kc</dt>
                <dd><input value={kc} onChange={(e) => setKc(e.target.value)} /></dd>
              </div>
              <div>
                <dt>Ti</dt>
                <dd><input value={ti} onChange={(e) => setTi(e.target.value)} /></dd>
              </div>
              <div>
                <dt>Td</dt>
                <dd><input value={td} onChange={(e) => setTd(e.target.value)} /></dd>
              </div>
            </dl>
            <button className="lv-pid-apply" disabled={!armado} onClick={() => void aplicarPid()}>Aplicar PID</button>
          </div>
        </section>
        <section className="lv-control-card lv-pid ca-sp">
          <h3>Setpoint</h3>
            <div className="ca-command">
              <KnobControl value={Number(sp)} max={140} ticks={[0, 20, 40, 60, 80, 100, 120, 140]}
                label={`Setpoint ${eq.unit}`} disabled={sim ? !plcOk : !armado} editable
                onChange={(v) => setSp(String(v))}
                onCommit={(v) => (sim ? plc.cargarSetpoint(v) : void mandar('Setpoint', v, undefined, 'L/min'))} />
            </div>
        </section>
        </div>

        <section className="lv-control-card ca-pert">
          <h3>Perturbación</h3>
          <p className="ca-pert-sub">% apertura válvula</p>
          <KnobControl value={Number(valvula)} max={100} ticks={[0, 20, 40, 60, 80, 100]} label="Apertura de válvula" disabled={sim ? !plcOk : !armado} editable onChange={(v) => setValvula(String(v))} />
          <button disabled={sim ? !plcOk : !armado} onClick={() => (sim ? undefined : void mandar('AjustarValvula', Number(valvula), undefined, '%'))}>{sim ? 'Válvula aplicada (simulador)' : 'Aplicar válvula'}</button>
        </section>

      </div>
        </div>
      </div>
      {historicoAbierto && <div className="co-modal" role="dialog" aria-modal="true" onClick={() => setHistoricoAbierto(false)}>
        <div className="co-modal-caja co-hist" onClick={(e) => e.stopPropagation()}>
          <div className="co-modal-head"><b><i className={online ? 'co-hist-dot on' : 'co-hist-dot'}>●</i> Histórico · caudal-mcc09</b><button onClick={() => setHistoricoAbierto(false)}>×</button></div>
          <dl className="co-modal-cuerpo co-hist-list">
            <dt>Tasa</dt><dd>1 segundo</dd>
            <dt>Muestras</dt><dd>{samples.length}</dd>
            <dt>Última lectura</dt><dd className={online ? undefined : 'nodata'}>{online ? timeOnly(eq.timestamp) : 'Sin datos'}</dd>
            <dt>Fuente</dt><dd>API REST + SignalR</dd>
          </dl>
        </div>
      </div>}
      {ordenesAbiertas && <div className="co-modal" role="dialog" aria-modal="true" onClick={() => setOrdenesAbiertas(false)}>
        <div className="co-modal-caja" onClick={(e) => e.stopPropagation()}>
          <div className="co-modal-head"><b>Órdenes de control · caudal-mcc09</b><button onClick={() => setOrdenesAbiertas(false)}>×</button></div>
          <div className="co-modal-cuerpo">
            {ordenes.length === 0 ? <p className="co-vacio">Sin órdenes todavía</p> : <ul className="co-list">
              {ordenes.map((o) => <li key={o.id} className="co-item">
                <b className={o.estado === 'Confirmado' ? 'ok' : ['Rechazado', 'Error', 'Timeout'].includes(o.estado) ? 'err' : 'wait'}>{o.estado}</b>
                <span>{o.tipo}{o.valor != null ? ` ${o.valor}` : ''}{o.parametro ? ` · ${o.parametro}` : ''}{o.motivo ? ` · ${o.motivo}` : ''}</span>
                <i className="co-hora">{new Date(o.expedida).toLocaleTimeString('es-PE', { hour12: false })}</i>
              </li>)}
            </ul>}
          </div>
          <div className="co-modal-pie">Modo REAL · cada orden exige escritura y lectura posterior coincidente</div>
        </div>
      </div>}
      <ConfirmarOrden abierto={confirmarInicio || confirmarDetencion} accion={confirmarDetencion ? 'Detener' : 'Iniciar'} equipo="caudal-mcc09" simulada={simulada}
        condiciones={[
          { etiqueta: 'PLC S7-200', valor: online ? 'CONECTADO' : 'DESCONECTADO', ok: online },
          { etiqueta: 'Selector físico', valor: estado(caudalSenal, 'estado/selector_remoto') ? 'REMOTO' : 'NO REMOTO', ok: estado(caudalSenal, 'estado/selector_remoto') === true },
          { etiqueta: 'Origen de mando', valor: estado(caudalSenal, 'estado/modo_hmi_pc') ? 'HMI' : 'PC', ok: !estado(caudalSenal, 'estado/modo_hmi_pc') },
          confirmarDetencion
            ? { etiqueta: 'Sistema en marcha', valor: estado(caudalSenal, 'estado/sistema_funcionando') ? 'SÍ' : 'NO' }
            : { etiqueta: 'Nivel bajo T1', valor: estado(caudalSenal, 'estado/nivel_bajo') ? 'ACTIVO' : 'NO', ok: !estado(caudalSenal, 'estado/nivel_bajo') },
          { etiqueta: 'Control del backend', valor: armado ? 'ARMADO' : 'BLOQUEADO', ok: armado },
        ]}
        efecto={confirmarDetencion ? 'pone M0.2 = 0 y detiene la bomba' : 'escribe M0.2 = 1 y arranca la bomba'}
        onCancelar={() => { setConfirmarInicio(false); setConfirmarDetencion(false); }}
        onConfirmar={() => { const det = confirmarDetencion; setConfirmarInicio(false); setConfirmarDetencion(false); void mandar(det ? 'Detener' : 'Iniciar'); }} />
    </div>
  );
}
