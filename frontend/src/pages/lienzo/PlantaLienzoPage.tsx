import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../../context/PlantContext';
import { api } from '../../services/api';
import type { LevelDetail } from '../../types';
import type { Route } from '../../router';
import { ErrorBlock, LoadingBlock } from '../../components/common/States';
import { IconLock } from '../../components/common/Icons';
import { Sparkline } from '../../components/charts/Sparkline';
import { AgentePanel } from '../../components/lienzo/panels/AgentePanel';
import { diagnosticoDe, type CtxLienzo } from './nodos';
import { EQUIPOS, ORGANIZACION, type EquipoLienzo } from './lienzoData';
import { ageSeconds, formatAge, isStale, moduleMeta, num, timeOnly } from '../../utils/format';
import type { Sev } from '../../lienzo/tipos';

type SevEquipo = 'normal' | 'aviso' | 'alarma' | 'sin_datos';

const TXT_SEV: Record<SevEquipo, string> = {
  normal: 'Operando',
  aviso: 'Atención',
  alarma: 'Alarma',
  sin_datos: 'Sin datos en vivo',
};

const RUTA: Record<string, Route> = {
  'caudal-mcc09': 'lienzo-caudal',
  'nivel-mcn09': 'lienzo-nivel',
  'presion-mcp09': 'lienzo-presion',
  'temp-mct09': 'lienzo-temp',
};

function Pill({ ok, txt }: { ok: boolean | undefined; txt: string }) {
  return (
    <span className={`lz-pill${ok === undefined ? '' : ok ? ' ok' : ' mal'}`}>
      <span className="lz-punto" />
      {txt}
    </span>
  );
}

const aSev = (sev: Sev): SevEquipo =>
  sev === 'alarma' ? 'alarma' : sev === 'aviso' ? 'aviso' : sev === 'inactivo' ? 'sin_datos' : 'normal';

/** Vista general de los lienzos: réplica de Planta.tsx de la tesis con datos reales. */
export function PlantaLienzoPage({ onNavigate }: { onNavigate: (route: Route) => void }) {
  const { equipment, historyFor, link, health, load, error, reload, now, senal, caudalSenal } = usePlant();
  const [detalle, setDetalle] = useState<LevelDetail | null>(null);

  useEffect(() => {
    let cancelado = false;
    api
      .levelDetail()
      .then((d) => {
        if (!cancelado) setDetalle(d);
      })
      .catch(() => {
        /* sin detalle disponible */
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const filas = useMemo(() => {
    return EQUIPOS.map((config: EquipoLienzo) => {
      const eq = equipment.find((e) => e.id === config.id);
      const muestras = historyFor(config.id);
      if (!eq) return { config, eq: null, sev: 'sin_datos' as SevEquipo, diag: null, spark: [] as Array<[string, number]> };

      const stale = isStale(now, eq.timestamp, 15);
      const ctx: CtxLienzo = {
        equipoId: config.id,
        eq,
        valor: eq.value ?? 0,
        tsActual: eq.timestamp,
        historico: false,
        fresco: !stale,
        online: eq.status === 'ONLINE',
        edad: formatAge(ageSeconds(now, eq.timestamp)),
        age: ageSeconds(now, eq.timestamp),
        momento: null,
        detalle,
        senal: config.id === 'caudal-mcc09' ? caudalSenal : config.id === 'nivel-mcn09' ? senal : null,
      };
      const diag = diagnosticoDe(ctx);
      const sev: SevEquipo = aSev(diag.sev);
      const spark = muestras.slice(-60).map((s) => [s.ts, s.value] as [string, number]);
      return { config, eq, sev, diag, spark, ctx };
    });
  }, [equipment, historyFor, now, detalle, senal, caudalSenal]);

  if (load === 'loading') return <LoadingBlock label="Cargando la vista de planta…" />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;

  const enLinea = filas.filter((f) => f.eq?.status === 'ONLINE').length;
  const atencion = filas.filter((f) => f.sev !== 'normal');

  return (
    <div className="lz-vista">
      <header className="lz-topbar">
        <div className="lz-marca">
          <div className="lz-logo" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div>
            <h1>
              {ORGANIZACION.area} · Vista general
            </h1>
            <p title={ORGANIZACION.unsRaiz}>
              {ORGANIZACION.campus} · aula {ORGANIZACION.aula} · UNS <code>{ORGANIZACION.unsRaiz}</code>
            </p>
          </div>
        </div>

        <div className="lz-estados">
          <Pill ok={health === 'ok' ? true : health === 'error' ? false : undefined} txt="API REST" />
          <Pill ok={link === 'connected' ? true : link === 'disconnected' ? false : undefined} txt="SignalR" />
          <span className="lz-pill">
            <span className="lz-punto" />
            {enLinea}/{EQUIPOS.length} equipos en línea
          </span>
          <span className="lz-pill lz-ro" title="Ninguna parte del lienzo puede escribir en el PLC">
            <IconLock width="13" height="13" /> Solo lectura
          </span>
        </div>
      </header>

      <div className="lz-planta">
        <main className="lz-planta-cuerpo">
          <section aria-labelledby="lz-t-equipos">
            <div className="lz-sec-cab">
              <h2 id="lz-t-equipos">Equipos integrados</h2>
              <small>Actualizado {timeOnly(now)} · en vivo por SignalR</small>
            </div>

            <div className="lz-tarjetas">
              {filas.map(({ config, eq, sev, diag, spark }) => {
                const meta = moduleMeta(config.id);
                const bomba = config.id === 'nivel-mcn09' && detalle;
                /* Sin telemetría viva no se muestra un 0.00 engañoso: va "--" */
                const conDato = Boolean(eq) && eq!.status === 'ONLINE' && sev !== 'sin_datos';
                /* la consigna está en la MISMA unidad que la variable principal (cm, L/min, psi, °C);
                   'secundario' es otra señal (p. ej. la frecuencia del variador en Hz) */
                const setpoint = eq && eq.setpoint > 0 ? num(eq.setpoint, config.principal.decimales) : null;
                return (
                  <article className={`lz-tarjeta sev-${sev}`} key={config.id}>
                    <header className="lz-tj-cab">
                      <div className="lz-tj-titulo">
                        <div className="lz-tj-cod">
                          {config.codigo} · {config.proceso}
                        </div>
                        <h2>{config.nombre}</h2>
                      </div>
                      <span className={`lz-tj-sem sev-${sev}`}>
                        <span className="lz-punto" />
                        {TXT_SEV[sev]}
                      </span>
                    </header>

                    <div className="lz-tj-medida">
                      <div className={`lz-tj-principal ${sev === 'alarma' ? 'alarma' : sev === 'aviso' ? 'aviso' : ''}`}>
                        <span className={`num${conDato ? '' : ' sin-dato'}`}>
                          {conDato ? num(eq!.value, config.principal.decimales) : '--'}
                        </span>
                        <span className="uni">{config.principal.unidad}</span>
                        <small>{config.principal.nombre}</small>
                      </div>
                      <div className="lz-tj-sec">
                        <small>Setpoint</small>
                        <b>{setpoint ? `${setpoint} ${config.principal.unidad}` : 'Sin datos'}</b>
                      </div>
                    </div>

                    {spark.length >= 2 ? (
                      <Sparkline
                        points={spark.map(([ts, v]) => ({ t: Date.parse(ts), v }))}
                        color={meta.color}
                        height={40}
                      />
                    ) : (
                      <div className="lz-tj-spark-vacio">Sin historial en el búfer</div>
                    )}

                    <div className="lz-tj-chips">
                      <span className="lz-chip">{config.id === 'nivel-mcn09' ? `Modo ${detalle?.mode ?? '—'}` : 'Modo —'}</span>
                      {bomba ? (
                        <span className={`lz-chip${detalle?.pumpOn ? ' on' : ''}`}>
                          Bomba {detalle?.pumpOn ? 'en marcha' : 'detenida'}
                        </span>
                      ) : null}
                      <span className={`lz-chip${eq?.status === 'ONLINE' ? ' on' : ' aviso'}`}>
                        PLC {eq ? eq.status.toLowerCase() : 'sin dato'}
                      </span>
                    </div>

                    <div className={`lz-tj-diag sev-${sev}`}>
                      <b>{diag?.nombre ?? 'Sin diagnóstico'}</b>
                      <span>{eq ? (diag?.explicacion ?? '') : 'Equipo no disponible en la API'}</span>
                    </div>

                    <footer className="lz-tj-pie">
                      <span title={`${config.plc} · ${config.ip}`}>
                        {config.plc} · {config.ip}
                      </span>
                      <button type="button" className="btn" onClick={() => onNavigate(RUTA[config.id])}>
                        Abrir lienzo →
                      </button>
                    </footer>
                  </article>
                );
              })}
            </div>
          </section>

        </main>

        <aside className="lz-planta-agente panel">
          <div className="panel-head">
            <div>
              <h2>Agente coordinador</h2>
              <span className="panel-sub">consulta a los equipos con herramientas de solo lectura</span>
            </div>
            <span className="readonly-tag">Solo lectura</span>
          </div>
          <AgentePanel />
        </aside>
      </div>

      <section className="lz-atencion lz-atencion-ancha" aria-labelledby="lz-t-atencion">
        <div className="lz-sec-cab">
          <h2 id="lz-t-atencion">Requiere atención</h2>
          <small>{atencion.length} equipo(s)</small>
        </div>
        {atencion.length === 0 ? (
          <div className="lz-vacio">Todos los equipos operan sin alarmas.</div>
        ) : (
          atencion.map(({ config, sev, diag }) => (
            <button
              type="button"
              key={config.id}
              className={`lz-aten-fila sev-${sev}`}
              onClick={() => onNavigate(RUTA[config.id])}
            >
              <span className="lz-punto" />
              <b>{config.codigo}</b>
              <span>
                {sev === 'sin_datos'
                  ? 'Sin datos en vivo: revisar comunicación con el PLC'
                  : `${diag?.nombre ?? 'Atención'}: ${diag?.explicacion ?? ''}`}
              </span>
            </button>
          ))
        )}
      </section>
    </div>
  );
}
