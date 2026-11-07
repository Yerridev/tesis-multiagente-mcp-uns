import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { LEVEL_ID, api } from '../services/api';
import type { LevelDetail, NivelSenales } from '../types';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart } from '../components/charts/TrendChart';
import { MimicDiagram } from '../components/scada/MimicDiagram';
import { ControlPanel, PidEditor, SetpointPerilla, ValvulaBotones, useModoReal } from '../components/scada/ControlPanel';
import { KnobRO } from '../components/scada/KnobRO';
import { ModuloHeader, type EstadoCom, type Modo } from '../components/scada/ModuloHeader';
import { HistoricoModal } from '../components/scada/HistoricoModal';
import { formatAge, ageSeconds, isStale, num, timeOnly, valorMedible } from '../utils/format';

function raw(s: NivelSenales | null, key: string): number | null {
  const value = s?.valores?.[key]?.valor;
  const n = Number(value);
  return value == null || !Number.isFinite(n) ? null : n;
}

function texto(s: NivelSenales | null, key: string): string | null {
  const value = s?.valores?.[key]?.valor;
  return value == null ? null : String(value).trim().toUpperCase();
}

export function LevelScadaPage() {
  const { byId, historyFor, load, error, reload, now, link, senal } = usePlant();
  const modoReal = useModoReal();
  const [detail, setDetail] = useState<LevelDetail | null>(null);
  const [modo, setModo] = useState<Modo>('real');
  const [historicoAbierto, setHistoricoAbierto] = useState(false);
  const level = byId[LEVEL_ID];

  useEffect(() => {
    let active = true;
    const loadDetail = () => api.levelDetail().then((d) => active && setDetail(d)).catch(() => undefined);
    loadDetail(); const timer = window.setInterval(loadDetail, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const samples = useMemo(() => historyFor(LEVEL_ID).slice(-300), [historyFor]);
  if (load === 'loading') return <LoadingBlock label="Cargando Scada Nivel…" />;
  if (load === 'error' || !level) return <ErrorBlock message={error ?? 'No se recibió el módulo de nivel.'} onRetry={reload} />;

  const stale = isStale(now, level.timestamp, 15);
  const age = ageSeconds(now, level.timestamp);
  const setpointRaw = raw(senal, 'pid/setpoint_a_raw');
  const setpoint = setpointRaw == null ? null : (16348 - setpointRaw) / 400;
  const kp = (raw(senal, 'pid/kc_a') ?? 0) / 100;
  const ti = (raw(senal, 'pid/ti_a') ?? 0) / 100;
  const td = (raw(senal, 'pid/td_a') ?? 0) / 100;
  const control = raw(senal, 'pid/cv_raw');
  const fuenteControl = texto(senal, 'estado/fuente_control');
  const valve = raw(senal, 'valvula/posicion_pct') ?? detail?.valveOpen ?? null;
  const online = level.status === 'ONLINE' && !stale;
  /* El conector edge publica nivel/fuera_rango_sensor cuando el sensor ultrasónico
     satura (o muere): el valor en cm es el TOPE de la escala (≈40,9 cm), no una medida.
     El backend lo marca además en la calidad del dato. */
  const nivelFueraDeRango =
    senal?.valores?.['nivel/fuera_rango_sensor']?.valor === true ||
    !valorMedible(level.calidad) ||
    !valorMedible(detail?.calidad);
  /* Frescura del EDGE: el heartbeat se publica cada 10 s. NO se usa la marca de tiempo
     de nivel/cm porque el edge solo re-publica esa señal cuando cambia o cada 60 s
     (con 15 s de ventana marcaría como obsoleta una lectura perfectamente válida). */
  const nivelFresco = !isStale(now, senal?.heartbeat ?? null, 25);
  const nivelValido = online && nivelFresco && !nivelFueraDeRango;


  const series = [
    { id: 'nivel', label: 'NIVEL', color: '#ef5350', points: samples.map(s => ({ t: Date.parse(s.ts), v: s.value })) },
    ...(setpoint == null ? [] : [{ id: 'sp', label: 'SETPOINT', color: '#ffd600', dashed: true, points: samples.map(s => ({ t: Date.parse(s.ts), v: setpoint })) }]),
  ];

  const estadoCom: EstadoCom = online ? 'conectado' : link === 'reconnecting' || link === 'connecting' ? 'reconectando' : 'sin-comunicacion';
  // SIMULADOR: solo cambia lo que se DIBUJA en el mímico; las órdenes quedan deshabilitadas.
  const sim = modo === 'simulador';
  const w = Math.sin(now / 2400);
  const levelSim = { ...level, status: 'ONLINE', value: 38 + w * 2, timestamp: new Date(now).toISOString() } as typeof level;
  const detailSim = { ...(detail ?? {}), pumpOn: true, tankHeight: 60, valveOpen: 61 } as LevelDetail;
  const senalSim = { valores: { 'valvula/abriendo': { valor: true }, 'valvula/cerrando': { valor: false }, 'estado/tanque1_con_agua': { valor: true }, 'estado/alarma_nivel_bajo_tanque1': { valor: false } } } as unknown as NivelSenales;

  return <div className="lv-scada">
    <ModuloHeader id={level.id} titulo="Módulo de control de nivel" meta="Allen-Bradley MicroLogix 1100 · 192.168.114.9 · telemetría y control real protegido" estado={estadoCom} modo={modo} onModoChange={setModo} />

    {!sim && !nivelValido && online && <p role="alert" style={{ margin: 0, padding: '8px 12px', background: '#fff3cd', color: '#7a4300', borderRadius: 8, fontWeight: 700, fontSize: 12 }}>{nivelFueraDeRango ? 'Sensor de nivel FUERA DE RANGO: el valor en cm que se mostraría es el tope de saturación de la escala, NO el nivel real. Verifica el sensor (24 VDC, cableado, módulo 1762-IF2OF2 canal I:1/1) y el nivel físico antes de controlar.' : 'Lectura de nivel no válida: dato desactualizado del edge. Verifica la comunicación antes de controlar.'}</p>}

    <div className="lv-main ca-layout">
      {sim
        ? <MimicDiagram level={levelSim} detail={detailSim} senal={senalSim} nivelValido />
        : <MimicDiagram level={level} detail={detail} senal={senal} nivelValido={nivelValido} />}

      {/* columna derecha: tendencia + paneles de control */}
      <div className="ca-side">
        <section className="lv-trend">
          <div className="lv-trend-head">
            <b>Tendencia del proceso</b>
            <div className="ca-trend-right">
              <span>{samples.length} muestras · {online ? (link === 'connected' ? 'en vivo' : link) : 'PLC sin datos'}</span>
              <span className={`pill ${modoReal ? 'pill-err' : 'pill-warn'}`}>{modoReal ? 'REAL' : 'DRY-RUN'}</span>
            </div>
          </div>
          <div className="lv-chart"><TrendChart series={series} unit="cm" size="tall" yTicks={[0, 10, 20, 30, 40, 50, 60]} timeTitle emptyText={nivelFueraDeRango ? 'El sensor de nivel está saturado: no hay medida que representar (el valor en cm sería el tope de la escala).' : ''} /></div>
          <div className="lv-chart-foot"><span>Última lectura</span><b>{online ? `${timeOnly(level.timestamp)} · ${formatAge(age)}` : 'Sin comunicación · módulo apagado'}</b></div>
        </section>

        <div className="lv-controls">
          <section className="lv-control-card lv-options"><h3>Opciones</h3>
            <fieldset className="co-fieldset" disabled={sim}><ControlPanel /></fieldset>
            <button type="button" className="co-ver" onClick={() => setHistoricoAbierto(true)}>Histórico</button>
          </section>

          <section className="lv-control-card lv-signals"><h3>Controlador</h3>
            <div className="ca-sig-table">
              <div><span>Selector físico</span><strong>{detail?.mode ?? 'Sin dato'}</strong></div>
              <div><span>Origen de mando</span><strong>{fuenteControl ?? 'Sin dato'}</strong></div>
              <div><span>Señal nivel</span><strong>{nivelValido ? `${num(level.value, 2)} cm` : 'Sin dato'}</strong></div>
              <div><span>Señal control</span><strong>{control == null || !nivelValido ? 'Sin dato' : `${num(control, 0)} cuentas`}</strong></div>
            </div>
          </section>

          <div className="ca-pid-col">
            <section className="lv-control-card lv-pid ca-sp"><h3>Setpoint</h3>
              <div className="ca-command"><SetpointPerilla actual={setpoint} deshabilitado={sim || nivelFueraDeRango} motivo={sim ? 'Simulador: sin órdenes al PLC.' : 'Consigna deshabilitada: el sensor de nivel está fuera de rango (baja el nivel del tanque).'} /></div>
            </section>
            <section className="lv-control-card lv-pid"><h3>Control PID</h3>
              <fieldset className="co-fieldset" disabled={sim}><PidEditor kp={kp} ti={ti} td={td} /></fieldset>
            </section>
          </div>

          <section className="lv-control-card lv-valve ca-pert"><h3>Apertura de válvula</h3>
            <p className="ca-pert-sub">% apertura</p>
            <KnobRO value={sim ? 61 : valve} max={100} ticks={[0, 20, 40, 60, 80, 100]} label="% apertura" />
            <div className="lv-valve-state"><span><i className={sim || raw(senal, 'valvula/abriendo') ? 'on' : ''} />Abriendo</span><span><i className={!sim && raw(senal, 'valvula/cerrando') ? 'on red' : ''} />Cerrando</span></div>
            <fieldset className="co-fieldset" disabled={sim}><ValvulaBotones disabled={false} /></fieldset>
          </section>
        </div>
      </div>
    </div>

    <HistoricoModal abierto={historicoAbierto} onClose={() => setHistoricoAbierto(false)} id={level.id} online={online} muestras={samples.length} ultima={timeOnly(level.timestamp)} fuente="MQTT / UNS" />
  </div>;
}
