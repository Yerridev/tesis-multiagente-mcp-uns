import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart } from '../components/charts/TrendChart';
import { PressureFlow, type PresionSenal } from '../components/scada/PressureFlow';
import { KnobRO as Knob } from '../components/scada/KnobRO';
import { ModuloHeader, type EstadoCom, type Modo } from '../components/scada/ModuloHeader';
import { HistoricoModal } from '../components/scada/HistoricoModal';
import { ageSeconds, formatAge, isStale, num, timeOnly } from '../utils/format';
import type { ControlOrden, PresionSenales } from '../types';
import { enviarControlPresion, estadoControlPresion, listarOrdenesPresion, tokenControl } from '../services/control';

const ID = 'presion-mcp09';

function real(s: PresionSenales | null, key: string): number | null {
  const v = s?.valores?.[key]?.valor;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'boolean') return v ? 1 : 0;
  const n = typeof v === 'string' ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}

function estado(s: PresionSenales | null, key: string): boolean | null {
  const v = real(s, key);
  return v == null ? null : v >= 0.5;
}

export function ModulePresionPage() {
  const { byId, historyFor, load, error, reload, now, link, presionSenal } = usePlant();
  const eq = byId[ID];
  const samples = useMemo(() => historyFor(ID).slice(-300), [historyFor]);
  const [armado, setArmado] = useState(false);
  const [mensaje, setMensaje] = useState('Comprobando control…');
  const [ordenes, setOrdenes] = useState<ControlOrden[]>([]);
  const [ordenesAbiertas, setOrdenesAbiertas] = useState(false);
  const [confirmarInicio, setConfirmarInicio] = useState(false);
  const [confirmarDetencion, setConfirmarDetencion] = useState(false);
  const [setpointPendiente, setSetpointPendiente] = useState(false);
  const [pidAplicando, setPidAplicando] = useState(false);
  const [modo, setModo] = useState<Modo>('real');
  const [historicoAbierto, setHistoricoAbierto] = useState(false);

  const cargarOrdenes = async () => {
    const r = await listarOrdenesPresion();
    if (r.ok && r.datos) {
      setOrdenes(r.datos);
      setSetpointPendiente(r.datos.some((o) => o.tipo === 'Setpoint' && !['Confirmado', 'Rechazado', 'Vencido', 'Timeout', 'Error'].includes(o.estado)));
    }
  };

  useEffect(() => {
    void estadoControlPresion().then((r) => {
      const ok = r.ok && r.datos?.datos.realArmado === true;
      setArmado(ok);
      setMensaje(ok ? 'Control REAL habilitado' : 'Control físico bloqueado hasta la puesta en marcha');
    });
    void cargarOrdenes();
  }, []);

  useEffect(() => {
    if (!ordenesAbiertas) return;
    const timer = window.setInterval(() => void cargarOrdenes(), 1000);
    return () => window.clearInterval(timer);
  }, [ordenesAbiertas]);

  const mandar = async (tipo: string, valor?: number, unidad?: string) => {
    if (tipo === 'Setpoint' && setpointPendiente) return;
    if (tipo === 'Setpoint') setSetpointPendiente(true);
    setMensaje(`Enviando ${tipo}…`);
    const r = await enviarControlPresion({ tipo, valor, unidad, comentario: 'Orden desde SCADA de presión' });
    setMensaje(r.ok ? `${tipo}: enviada; esperando lectura posterior` : `${tipo}: ${r.error ?? 'rechazado'}`);
    if (!r.ok || tipo !== 'Setpoint') {
      if (tipo === 'Setpoint') setSetpointPendiente(false);
      window.setTimeout(() => void cargarOrdenes(), 500);
      return;
    }
    const id = typeof r.datos?.id === 'string' ? r.datos.id : null;
    for (let intento = 0; intento < 15; intento += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      const lista = await listarOrdenesPresion();
      if (!lista.ok || !lista.datos) continue;
      setOrdenes(lista.datos);
      const actual = id ? lista.datos.find((o) => o.id === id) : lista.datos[0];
      if (actual && ['Confirmado', 'Rechazado', 'Vencido', 'Timeout', 'Error'].includes(actual.estado)) {
        setMensaje(`Setpoint: ${actual.estado}${actual.motivo ? ` · ${actual.motivo}` : ''}`);
        setSetpointPendiente(false);
        return;
      }
    }
    setSetpointPendiente(false);
  };

  const esperarTerminal = async (id: string): Promise<ControlOrden | null> => {
    for (let intento = 0; intento < 20; intento += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 750));
      const lista = await listarOrdenesPresion();
      if (!lista.ok || !lista.datos) continue;
      setOrdenes(lista.datos);
      const actual = lista.datos.find((o) => o.id === id);
      if (actual && ['Confirmado', 'Rechazado', 'Vencido', 'Timeout', 'Error'].includes(actual.estado)) return actual;
    }
    return null;
  };

  const aplicarPidDocumentado = async () => {
    if (pidAplicando) return;
    setPidAplicando(true);
    const valores = [
      { parametro: 'kp', valor: 3 },
      { parametro: 'ti', valor: 0.1 },
      { parametro: 'td', valor: 0 },
    ];
    try {
      for (const ajuste of valores) {
        setMensaje(`Aplicando PID: ${ajuste.parametro}=${ajuste.valor}…`);
        const r = await enviarControlPresion({
          tipo: 'ParametroPid', parametro: ajuste.parametro, valor: ajuste.valor,
          comentario: 'PID predeterminado documentado en el manual físico',
        });
        if (!r.ok || !r.datos?.id) {
          setMensaje(`PID no aplicado: ${r.error ?? ajuste.parametro}`);
          return;
        }
        const final = await esperarTerminal(r.datos.id);
        if (!final || final.estado !== 'Confirmado') {
          setMensaje(`PID incompleto en ${ajuste.parametro}: ${final?.motivo ?? final?.estado ?? 'SIN_CONFIRMACION'}`);
          return;
        }
      }
      setMensaje('PID confirmado: Kp=3.00 · Ti=0.10 · Td=0.00');
    } finally {
      setPidAplicando(false);
      void cargarOrdenes();
    }
  };

  if (load === 'loading') return <LoadingBlock label="Cargando Scada Presión…" />;
  if (load === 'error' || !eq) return <ErrorBlock message={error ?? 'No se recibió el módulo de presión.'} onRetry={reload} />;

  const age = ageSeconds(now, eq.timestamp);
  const stale = isStale(now, eq.timestamp, 15);
  // Telemetría real: el módulo está en línea si el edge MQTT siguepublicando
  // y el cFP-2200 reporta conexión activa.
  const senalAge = presionSenal?.ultimo ? ageSeconds(now, presionSenal.ultimo) : Number.POSITIVE_INFINITY;
  const online = presionSenal?.mqtt === true && presionSenal.plc === 'CONECTADO' && (senalAge ?? Number.POSITIVE_INFINITY) <= 15 && !stale;

  const psi = real(presionSenal, 'presion/psi');
  const mA = real(presionSenal, 'presion/transmisor_ma');
  const spPc = real(presionSenal, 'pid/setpoint_pc');
  const kp = real(presionSenal, 'pid/kp');
  const ti = real(presionSenal, 'pid/ti');
  const td = real(presionSenal, 'pid/td');
  const cv = real(presionSenal, 'pid/cv');
  const variadorV = real(presionSenal, 'bomba/salida_variador');
  const valvulaV = real(presionSenal, 'valvula/salida');
  const valvulaPct = valvulaV == null ? null : valvulaV * 10;   // 1 V = 10 % de apertura
  const variadorPct = variadorV == null ? null : variadorV * 10;
  const auto = estado(presionSenal, 'estado/selector_remoto');
  const manual = estado(presionSenal, 'estado/selector_local');
  const controlPc = estado(presionSenal, 'estado/control_pc');
  const marcha = estado(presionSenal, 'estado/sistema_funcionando');
  const bombaOn = estado(presionSenal, 'estado/bomba_habilitada');
  const presostato = estado(presionSenal, 'estado/presostato');
  const alarmaAlta = estado(presionSenal, 'estado/alarma_nivel_alto');
  const alarmaBaja = estado(presionSenal, 'estado/alarma_nivel_bajo');

  const setpoint = spPc ?? (eq.setpoint > 0 ? eq.setpoint : null);
  const ultimaOrdenSetpoint = ordenes.find((o) => o.tipo === 'Setpoint');
  const solicitadoSp = ultimaOrdenSetpoint?.valor ?? null;
  const confirmadoSp = ultimaOrdenSetpoint?.estado === 'Confirmado' ? ultimaOrdenSetpoint.valorLeido : null;
  const series = [
    { id: 'presion', label: 'PRESIÓN', color: '#e2412d', points: samples.map((s) => ({ t: Date.parse(s.ts), v: s.value })) },
    ...(setpoint == null
      ? []
      : [{ id: 'sp', label: 'SETPOINT', color: '#ffd600', dashed: true, points: samples.map((s) => ({ t: Date.parse(s.ts), v: setpoint })) }]),
  ];

  // Señales reales del cFP-2200; lo que no exista queda en null ("Sin dato").
  const senal: PresionSenal = {
    online,
    presion: psi ?? (online ? eq.value : null),
    nivelPct: null,
    bomba: bombaOn ?? marcha,
    valvulaPct,
    valvulas: { V1: null, V2: null, V3: null, V4: null, V5: null, V6: null, V7: null },
    nivelAlto: alarmaAlta,
    nivelBajo: alarmaBaja,
  };

  const estadoCom: EstadoCom = online ? 'conectado' : link === 'reconnecting' || link === 'connecting' ? 'reconectando' : 'sin-comunicacion';
  // SIMULADOR: solo cambia lo que se DIBUJA en el mímico; las órdenes quedan deshabilitadas.
  const sim = modo === 'simulador';
  const w = Math.sin(now / 2400);
  const senalSim: PresionSenal = {
    online: true, presion: 31.8 + w * 1.1, nivelPct: 71 + w * 2, bomba: true, valvulaPct: 58,
    valvulas: { V1: true, V2: true, V3: false, V4: false, V5: true, V6: false, V7: false },
    nivelAlto: false, nivelBajo: false,
  };
  const puedeSp = !sim && armado && online && auto === true && controlPc === true && marcha === false && !setpointPendiente && !pidAplicando;

  return (
    <div className="lv-scada">
      <ModuloHeader
        id={eq.id}
        titulo="Módulo de control de presión"
        meta="NI Compact FieldPoint cFP-2200 · 192.168.114.8 · telemetría y control real protegido"
        estado={estadoCom}
        modo={modo}
        onModoChange={setModo}
      />

      <div className="lv-main ca-layout">
        <section className="panel mimic-panel ca-flow pr-flow">
          <div className="panel-head"><div><h2>Diagrama mímico</h2></div></div>
          <PressureFlow senal={sim ? senalSim : senal} />
        </section>

        {/* columna derecha: tendencia + paneles de control */}
        <div className="ca-side">
          <section className="lv-trend">
            <div className="lv-trend-head">
              <b>Tendencia del proceso</b>
              <div className="ca-trend-right">
                <span>{samples.length} muestras · {online ? (link === 'connected' ? 'en vivo' : link) : 'PLC sin datos'}</span>
                <span className={`pill ${armado ? 'pill-err' : 'pill-warn'}`}>{armado ? 'REAL' : 'BLOQUEADO'}</span>
              </div>
            </div>
            <div className="lv-chart">
              <TrendChart series={series} unit="PSI" size="tall" yTicks={[0, 10, 20, 30, 40, 50, 60]} timeTitle emptyText="Sin telemetría de presión · esperando el PLC NI cFP-2200…" />
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
              <small>{tokenControl()} · supervisor</small>
              <div className="lv-opt-btns">
                <button
                  disabled={sim || !armado || !online || setpointPendiente || pidAplicando}
                  title={armado ? 'El SCADA toma el mando del supervisor del cFP-2200 y arranca la bomba' : 'Control REAL no habilitado'}
                  onClick={() => setConfirmarInicio(true)}
                >Iniciar</button>
                <button
                  disabled={sim || !armado || !online}
                  title={armado ? 'El SCADA cede el mando y detiene la bomba' : 'Control REAL no habilitado'}
                  onClick={() => setConfirmarDetencion(true)}
                >Detener</button>
              </div>
              <small>{mensaje}</small>
            </section>

            <section className="lv-control-card lv-signals">
              <h3>Controlador</h3>
              <div className="ca-sig-table">
                <div><span>Controlador</span><strong>{eq.controller || 'Sin dato'}</strong></div>
                <div><span>Señal presión</span><strong>{psi != null ? `${num(psi, 2)} psi` : 'Sin dato'}</strong></div>
                <div><span>Transmisor</span><strong>{mA != null ? `${num(mA, 2)} mA` : 'Sin dato'}</strong></div>
                <div><span>Mando</span><strong>{auto ? 'AUTOMÁTICO' : manual ? 'MANUAL' : 'Sin dato'}</strong></div>
                <div><span>Supervisor</span><strong>{controlPc == null ? 'Sin dato' : controlPc ? 'PC / SCADA' : 'HMI LOCAL'}</strong></div>
                <div><span>Sistema</span><strong>{marcha == null ? 'Sin dato' : marcha ? 'EN MARCHA' : 'PARADO'}</strong></div>
                <div><span>Presostato</span><strong>{presostato == null ? 'Sin dato' : presostato ? 'ACTIVO' : 'NO ACTIVO'}</strong></div>
                <div><span>Variador</span><strong>{variadorPct != null ? `${num(variadorPct, 0)} %` : 'Sin dato'}</strong></div>
              </div>
            </section>

            <div className="ca-pid-col">
              <section className="lv-control-card lv-pid ca-sp">
                <h3>Setpoint</h3>
                <div className="ca-command">
                  <Knob
                    value={setpoint}
                    max={40}
                    ticks={[0, 10, 20, 30, 40]}
                    label={`Setpoint ${eq.unit}`}
                    onCommit={puedeSp ? (valor) => void mandar('Setpoint', valor, 'psi') : undefined}
                  />
                </div>
              </section>
              <section className="lv-control-card lv-pid">
                <h3>Control PID</h3>
                <div className="lv-pid-body">
                  <dl>
                    <div><dt>Kp</dt><dd className="ca-pid-ro">{kp != null ? num(kp, 2) : '—'}</dd></div>
                    <div><dt>Ti</dt><dd className="ca-pid-ro">{ti != null ? num(ti, 3) : '—'}</dd></div>
                    <div><dt>Td</dt><dd className="ca-pid-ro">{td != null ? num(td, 3) : '—'}</dd></div>
                  </dl>
                  <button
                    type="button"
                    className="lv-pid-apply"
                    disabled={sim || !armado || !online || auto !== true || controlPc !== true || marcha !== false || setpointPendiente || pidAplicando}
                    onClick={() => void aplicarPidDocumentado()}
                  >
                    {pidAplicando ? 'Aplicando y verificando…' : 'Aplicar PID documentado'}
                  </button>
                </div>
              </section>
            </div>

            <section className="lv-control-card ca-pert">
              <h3>Perturbación</h3>
              <p className="ca-pert-sub">% apertura válvula</p>
              <Knob value={sim ? 58 : valvulaPct} max={100} ticks={[0, 20, 40, 60, 80, 100]} label="Apertura de válvula" />
            </section>
          </div>
        </div>
      </div>

      <HistoricoModal abierto={historicoAbierto} onClose={() => setHistoricoAbierto(false)} id={eq.id} online={online} muestras={samples.length} ultima={timeOnly(eq.timestamp)} fuente="API REST + SignalR" />
      {ordenesAbiertas && (
        <div className="co-modal" role="dialog" aria-modal="true" onClick={() => setOrdenesAbiertas(false)}>
          <div className="co-modal-caja" onClick={(e) => e.stopPropagation()}>
            <div className="co-modal-head">
              <b>Órdenes de control · presion-mcp09</b>
              <button onClick={() => setOrdenesAbiertas(false)}>×</button>
            </div>
            <div className="co-modal-cuerpo">
              {ordenes.length === 0 ? (
                <p className="co-vacio">Sin órdenes todavía.</p>
              ) : (
                <div className="co-list">
                  {ordenes.map((o) => (
                    <div className="co-item" key={o.id}>
                      <span>{o.tipo}{o.parametro ? ` ${o.parametro}` : ''}{o.valor != null ? ` = ${o.valor}${o.unidad ? ` ${o.unidad}` : ''}` : ''}</span>
                      <b className={o.estado === 'Confirmado' ? 'ok' : ['Rechazado', 'Error', 'Timeout'].includes(o.estado) ? 'err' : 'wait'}>
                        {o.estado}
                      </b>
                      <small>{o.motivo ?? o.comentario ?? ''}</small>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="co-modal-pie">
              Modo REAL · cada orden escribe en el cFP-2200 y exige lectura posterior coincidente
            </div>
          </div>
        </div>
      )}

      {confirmarInicio && (
        <div className="co-modal" role="dialog" aria-modal="true" onClick={() => setConfirmarInicio(false)}>
          <div className="co-modal-caja co-confirm" onClick={(e) => e.stopPropagation()}>
            <div className="co-modal-head">
              <b>Confirmar inicio · presion-mcp09</b>
              <button onClick={() => setConfirmarInicio(false)}>×</button>
            </div>
            <div className="co-modal-cuerpo">
              <p><b>Condiciones verificadas antes de enviar:</b></p>
              <ul>
                <li>PLC: {online ? 'CONECTADO' : 'DESCONECTADO'}</li>
                <li>Selector físico: {auto ? 'AUTOMÁTICO' : 'NO AUTOMÁTICO (BLOQUEADO)'}</li>
                <li>Sistema en marcha: {marcha ? 'SÍ' : 'NO'}</li>
                <li>Presión actual: {psi != null ? `${num(psi, 2)} psi` : 'sin dato'}</li>
                <li>Modo del backend: {armado ? 'REAL' : 'BLOQUEADO'}</li>
              </ul>
              <p className="co-real-warning">
                MODO REAL: esta orden escribe INICIO_PC en el cFP-2200, el SCADA toma el mando del
                supervisor y la bomba puede arrancar físicamente.
              </p>
            </div>
            <div className="co-confirm-actions">
              <button onClick={() => setConfirmarInicio(false)}>Cancelar</button>
              <button className="danger" onClick={() => { setConfirmarInicio(false); void mandar('Iniciar'); }}>
                Confirmar e iniciar
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmarDetencion && (
        <div className="co-modal" role="dialog" aria-modal="true" onClick={() => setConfirmarDetencion(false)}>
          <div className="co-modal-caja co-confirm" onClick={(e) => e.stopPropagation()}>
            <div className="co-modal-head">
              <b>Confirmar detención · presion-mcp09</b>
              <button onClick={() => setConfirmarDetencion(false)}>×</button>
            </div>
            <div className="co-modal-cuerpo">
              <p><b>Condiciones verificadas antes de enviar:</b></p>
              <ul>
                <li>PLC: {online ? 'CONECTADO' : 'DESCONECTADO'}</li>
                <li>Selector físico: {auto ? 'AUTOMÁTICO' : 'NO AUTOMÁTICO (BLOQUEADO)'}</li>
                <li>Sistema en marcha: {marcha ? 'SÍ' : 'NO'}</li>
                <li>Presión actual: {psi != null ? `${num(psi, 2)} psi` : 'sin dato'}</li>
                <li>Modo del backend: {armado ? 'REAL' : 'BLOQUEADO'}</li>
              </ul>
              <p className="co-real-warning">
                MODO REAL: esta orden escribe SALIR_PC en el cFP-2200, el SCADA cede el mando y la
                bomba se detiene físicamente.
              </p>
            </div>
            <div className="co-confirm-actions">
              <button onClick={() => setConfirmarDetencion(false)}>Cancelar</button>
              <button className="danger" onClick={() => { setConfirmarDetencion(false); void mandar('Detener'); }}>
                Confirmar y detener
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
