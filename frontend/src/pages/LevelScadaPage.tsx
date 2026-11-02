import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../context/PlantContext';
import { LEVEL_ID, api } from '../services/api';
import type { LevelDetail, NivelSenales } from '../types';
import { ErrorBlock, LoadingBlock } from '../components/common/States';
import { TrendChart } from '../components/charts/TrendChart';
import { MimicDiagram } from '../components/scada/MimicDiagram';
import { ControlPanel, PidEditor, SetpointPerilla, ValvulaBotones, useModoReal } from '../components/scada/ControlPanel';
import { KnobRO } from '../components/scada/KnobRO';
import { formatAge, ageSeconds, isStale, num, timeOnly } from '../utils/format';

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
  const series = [
    { id: 'nivel', label: 'NIVEL', color: '#ef5350', points: samples.map(s => ({ t: Date.parse(s.ts), v: s.value })) },
    ...(setpoint == null ? [] : [{ id: 'sp', label: 'SETPOINT', color: '#ffd600', dashed: true, points: samples.map(s => ({ t: Date.parse(s.ts), v: setpoint })) }]),
  ];

  return <div className="lv-scada">
    <div className="lv-title"><div><span>MCN-09/001</span><h2>Módulo de control de nivel</h2></div><div className={`lv-live ${online ? 'on' : ''}`}><i />{online ? 'PLC conectado' : 'Sin comunicación'}</div></div>

    <div className="lv-main">
      {/* Diagrama mimico junto a la tendencia del proceso */}
      <MimicDiagram level={level} detail={detail} senal={senal} />

      <section className="lv-trend">
        <div className="lv-trend-head"><div><b>Tendencia del proceso</b><small>Nivel y consigna en centímetros</small></div><span>{samples.length} muestras · {online ? (link === 'connected' ? 'en vivo' : link) : 'PLC sin datos'}</span></div>
          <div className="lv-chart"><TrendChart series={series} unit="cm" size="tall" yTicks={[0, 10, 20, 30, 40, 50, 60]} timeTitle emptyText="Sin módulo en laboratorio · esperando lecturas del PLC…" /></div>
          <div className="lv-chart-foot"><span>Última lectura</span><b>{online ? `${timeOnly(level.timestamp)} · ${formatAge(age)}` : 'Sin comunicación · módulo apagado'}</b></div>
      </section>
    </div>

    <div className="lv-controls">
      <section className="lv-control-card lv-options"><h3>Opciones</h3>
        <ControlPanel />
        <a className="co-hist" href="#/history">Histórico</a>
      </section>

      <section className="lv-control-card lv-signals"><h3>Controlador</h3><div><span>Selector físico</span><b>{detail?.mode ?? 'Sin dato'}</b></div><div><span>Origen de mando</span><b>{fuenteControl ?? 'Sin dato'}</b></div><div><span>Señal nivel</span><strong>{online ? `${num(level.value, 2)} cm` : 'Sin dato'}</strong></div><div><span>Señal control</span><strong>{control == null ? 'Sin dato' : `${num(control, 0)} cuentas`}</strong></div></section>

      <section className="lv-control-card lv-pid"><h3>PID y setpoint</h3><div className="lv-pid-body"><PidEditor kp={kp} ti={ti} td={td} /><SetpointPerilla actual={setpoint} /></div></section>

      <section className="lv-control-card lv-record"><h3>Registro</h3><div className="lv-rec-icon">●</div><div><span>Estado</span><b>Histórico activo</b></div><div><span>Actualización</span><b>1 segundo</b></div><div><span>Fuente</span><b>MQTT / UNS</b></div></section>

      <section className="lv-control-card lv-valve"><h3>Apertura de válvula</h3><KnobRO value={valve} max={100} ticks={[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]} label="% apertura" /><div className="lv-valve-state"><span><i className={raw(senal, 'valvula/abriendo') ? 'on' : ''} />Abriendo</span><span><i className={raw(senal, 'valvula/cerrando') ? 'on red' : ''} />Cerrando</span></div><ValvulaBotones disabled={false} /></section>
    </div>
  </div>;
}
