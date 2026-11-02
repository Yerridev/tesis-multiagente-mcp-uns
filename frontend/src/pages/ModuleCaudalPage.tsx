import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart } from '../components/charts/TrendChart';
import { CaudalFlow, type CaudalSenal } from '../components/scada/CaudalFlow';
import { KnobControl } from '../components/scada/KnobControl';
import { ageSeconds, formatAge, num, timeOnly } from '../utils/format';
import type { CaudalSenales, ControlOrden } from '../types';
import { enviarControlCaudal, estadoControlCaudal, listarOrdenesCaudal, tokenControl } from '../services/control';

const ID = 'caudal-mcc09';

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
  const [sp, setSp] = useState('10');
  const [valvula, setValvula] = useState('100');
  const [kc, setKc] = useState('1');
  const [ti, setTi] = useState('0.01');
  const [td, setTd] = useState('0');
  const [ordenes, setOrdenes] = useState<ControlOrden[]>([]);
  const [ordenesAbiertas, setOrdenesAbiertas] = useState(false);
  const [confirmarInicio, setConfirmarInicio] = useState(false);
  const [confirmarDetencion, setConfirmarDetencion] = useState(false);
  const [usuario, setUsuario] = useState(tokenControl());

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

  return (
    <div className="lv-scada">
      <div className="lv-title">
        <div>
          <span>{eq.id}</span>
          <h2>Módulo de control de caudal</h2>
        </div>
        <div className={`lv-live ${online ? 'on' : ''}`}>
          <i />
          {online ? 'PLC conectado' : 'Sin comunicación'}
        </div>
      </div>

      <div className="lv-main">
        <section className="panel mimic-panel ca-flow">
          <div className="panel-head">
            <div>
              <h2>Diagrama mímico</h2>
              <span className="panel-sub">
                {eq.controller} · {eq.ip} · telemetría y control real protegido
              </span>
            </div>
            <div className="mimic-chips">
              <span className={`pill ${online ? 'pill-ok pill-live' : 'pill-err'}`}>
                <i />
                {online ? 'PLC conectado' : 'Sin comunicación'}
              </span>
              {!online && <span className="pill pill-warn">Válvulas en posición nominal</span>}
            </div>
          </div>
          <CaudalFlow senal={senal} />
        </section>

        <section className="lv-trend">
          <div className="lv-trend-head">
            <div>
              <b>Tendencia del proceso</b>
              <small>Caudal y consigna en L/min</small>
            </div>
            <span>
              {samples.length} muestras · {online ? (link === 'connected' ? 'en vivo' : link) : 'PLC sin datos'}
            </span>
          </div>
          <div className="lv-chart">
            <TrendChart
              series={series}
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
      </div>

      <div className="lv-controls">
        <section className="lv-control-card lv-options">
          <h3>Opciones</h3>
          <div className="co-top">
            <span className={`pill ${armado ? 'pill-err' : 'pill-warn'}`}>{armado ? 'REAL' : 'BLOQUEADO'}</span>
            <button type="button" className="co-ver" onClick={() => { setOrdenesAbiertas(true); void cargarOrdenes(); }}>
              Órdenes <span className={ordenes.length ? 'co-cont' : 'co-cont vacio'}>{ordenes.length}</span>
            </button>
          </div>
          <small>{usuario} · supervisor</small>
          <div className="lv-opt-btns">
            <button disabled={!armado || !online} onClick={() => setConfirmarInicio(true)}>Iniciar</button>
            <button disabled={!armado || !online} onClick={() => setConfirmarDetencion(true)}>Detener</button>
          </div>
          <small>{mensaje}</small>
        </section>

        <section className="lv-control-card lv-signals">
          <h3>Controlador</h3>
          <div>
            <span>Controlador</span>
            <b>{estado(caudalSenal, 'estado/selector_remoto') ? 'REMOTO' : estado(caudalSenal, 'estado/selector_local') ? 'LOCAL' : 'Sin dato'}</b>
          </div>
          <div>
            <span>Señal caudal</span>
            <strong>{online && liveCaudal != null ? `${num(liveCaudal, 1)} L/min` : 'Sin dato'}</strong>
          </div>
          <div>
            <span>Señal control</span>
            <strong>{real(caudalSenal, 'actuadores/variador_pct') == null ? 'Sin dato' : `${num(real(caudalSenal, 'actuadores/variador_pct')!, 1)} %`}</strong>
          </div>
        </section>

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
            <div className="ca-command">
              <KnobControl value={Number(sp)} max={140} ticks={[0, 20, 40, 60, 80, 100, 120, 140]}
                label={`Setpoint ${eq.unit}`} disabled={!armado}
                onChange={(v) => setSp(String(v))}
                onCommit={(v) => void mandar('Setpoint', v, undefined, 'L/min')} />
              <input type="number" min="0" max="140" value={sp}
                onChange={(e) => setSp(e.target.value)}
                onBlur={() => { if (armado) void mandar('Setpoint', Number(sp), undefined, 'L/min'); }}
                onKeyDown={(e) => { if (e.key === 'Enter' && armado) void mandar('Setpoint', Number(sp), undefined, 'L/min'); }} />
            </div>
          </div>
          <button disabled={!armado} onClick={() => void aplicarPid()}>Aplicar PID</button>
        </section>

        <section className="lv-control-card ca-pert">
          <h3>Perturbación</h3>
          <p className="ca-pert-sub">% apertura válvula</p>
          <KnobControl value={Number(valvula)} max={100} ticks={[0, 20, 40, 60, 80, 100]} label="Apertura de válvula" disabled={!armado} onChange={(v) => setValvula(String(v))} />
          <input type="number" min="0" max="100" value={valvula} onChange={(e) => setValvula(e.target.value)} />
          <button disabled={!armado} onClick={() => void mandar('AjustarValvula', Number(valvula), undefined, '%')}>Aplicar válvula</button>
        </section>

        <section className="lv-control-card lv-record">
          <h3>Histórico</h3>
          <div className="lv-rec-icon">●</div>
          <div>
            <span>Tasa</span>
            <b>1 segundo</b>
          </div>
          <div>
            <span>Muestras</span>
            <b>{samples.length}</b>
          </div>
          <div>
            <span>Última lectura</span>
            <b className={online ? undefined : 'nodata'}>{online ? timeOnly(eq.timestamp) : 'Sin datos'}</b>
          </div>
          <div>
            <span>Fuente</span>
            <b>API REST + SignalR</b>
          </div>
        </section>
      </div>
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
      {confirmarInicio && <div className="co-modal" role="dialog" aria-modal="true" onClick={() => setConfirmarInicio(false)}>
        <div className="co-modal-caja co-confirm" onClick={(e) => e.stopPropagation()}>
          <div className="co-modal-head"><b>Confirmar inicio · caudal-mcc09</b><button onClick={() => setConfirmarInicio(false)}>×</button></div>
          <div className="co-modal-cuerpo">
            <p><b>Condiciones verificadas antes de enviar:</b></p>
            <ul>
              <li>PLC: {online ? 'CONECTADO' : 'DESCONECTADO'}</li>
              <li>Selector físico: {estado(caudalSenal, 'estado/selector_remoto') ? 'REMOTO' : 'NO REMOTO'}</li>
              <li>Origen de mando: {estado(caudalSenal, 'estado/modo_hmi_pc') ? 'HMI (BLOQUEADO)' : 'PC'}</li>
              <li>Nivel bajo: {estado(caudalSenal, 'estado/nivel_bajo') ? 'ACTIVO (BLOQUEADO)' : 'NO'}</li>
              <li>Modo del backend: {armado ? 'REAL' : 'BLOQUEADO'}</li>
            </ul>
            <p className="co-real-warning">MODO REAL: esta orden escribirá M0.2 y accionará físicamente la bomba.</p>
          </div>
          <div className="co-confirm-actions"><button onClick={() => setConfirmarInicio(false)}>Cancelar</button><button className="danger" onClick={() => { setConfirmarInicio(false); void mandar('Iniciar'); }}>Confirmar e iniciar</button></div>
        </div>
      </div>}
      {confirmarDetencion && <div className="co-modal" role="dialog" aria-modal="true" onClick={() => setConfirmarDetencion(false)}>
        <div className="co-modal-caja co-confirm" onClick={(e) => e.stopPropagation()}>
          <div className="co-modal-head"><b>Confirmar detenci&oacute;n &middot; caudal-mcc09</b><button onClick={() => setConfirmarDetencion(false)}>&times;</button></div>
          <div className="co-modal-cuerpo">
            <p><b>Condiciones verificadas antes de enviar:</b></p>
            <ul>
              <li>PLC: {online ? 'CONECTADO' : 'DESCONECTADO'}</li>
              <li>Selector f&iacute;sico: {estado(caudalSenal, 'estado/selector_remoto') ? 'REMOTO' : 'NO REMOTO'}</li>
              <li>Origen de mando: {estado(caudalSenal, 'estado/modo_hmi_pc') ? 'HMI (BLOQUEADO)' : 'PC'}</li>
              <li>Sistema en marcha: {estado(caudalSenal, 'estado/sistema_funcionando') ? 'SI' : 'NO'}</li>
              <li>Modo del backend: {armado ? 'REAL' : 'BLOQUEADO'}</li>
            </ul>
            <p className="co-real-warning">MODO REAL: esta orden pondr&aacute; M0.2 en 0 y detendr&aacute; f&iacute;sicamente la bomba.</p>
          </div>
          <div className="co-confirm-actions"><button onClick={() => setConfirmarDetencion(false)}>Cancelar</button><button className="danger" onClick={() => { setConfirmarDetencion(false); void mandar('Detener'); }}>Confirmar y detener</button></div>
        </div>
      </div>}
    </div>
  );
}
