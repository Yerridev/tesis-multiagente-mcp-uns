import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../../context/PlantContext';
import { api } from '../../services/api';
import type { LevelDetail } from '../../types';
import type { Route } from '../../router';
import { ErrorBlock, LoadingBlock } from '../../components/common/States';
import { IconLock } from '../../components/common/Icons';
import { TimeBar } from '../../components/lienzo/TimeBar';
import VistaEquipo from '../../lienzo/VistaEquipo';
import { PanelesCtx } from '../../lienzo/paneles';
import { Ctx, resalteDe, type Estado } from '../../lienzo/ctx';
import { AccCtx, type Acciones } from '../../lienzo/acciones';
import { aristasDe, diagnosticoDe, lecturasDe, metasDe, panelesDe, senalModo, type CtxLienzo } from './nodos';
import { ageSeconds, formatAge, isStale, timeOnly } from '../../utils/format';
import type { EquipoLienzo } from './lienzoData';

interface Props {
  equipo: EquipoLienzo;
  onNavigate: (route: Route) => void;
}

/** Acciones estables del lienzo (portadas de acciones.ts de la tesis). */
const ACCIONES: Acciones = {
  agenteToca: () => {},
  agenteCadena: () => {},
  irA: () => {},
  nodosDeVariables: () => [],
};

function Pill({ ok, txt }: { ok: boolean | undefined; txt: string }) {
  return (
    <span className={`lz-pill${ok === undefined ? '' : ok ? ' ok' : ' mal'}`}>
      <span className="lz-punto" />
      {txt}
    </span>
  );
}

/**
 * Lienzo de un equipo: réplica de VistaEquipo.tsx de la tesis sobre ReactFlow.
 * Los 4 paneles (Diagnóstico, Agente de IA, Tendencia y Unified Namespace)
 * viven DENTRO del canvas como nodos `panel`, igual que en la tesis; el
 * sidebar y el header de la aplicación son los de MCP-INDUSTRIAL-NET.
 */
export function LienzoPage({ equipo, onNavigate }: Props) {
  const { byId, load, error, reload, now, link, health, historyFor, senal, caudalSenal, presionSenal, temperaturaSenal } = usePlant();
  const [momento, setMomento] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<LevelDetail | null>(null);
  const eq = byId[equipo.id];
  const samples = historyFor(equipo.id);

  const age = eq ? ageSeconds(now, eq.timestamp) : null;
  const stale = eq ? isStale(now, eq.timestamp, 15) : true;
  const historico = momento !== null;

  useEffect(() => {
    if (equipo.id !== 'nivel-mcn09') return;
    let cancelado = false;
    const tick = () => {
      api
        .levelDetail()
        .then((d) => {
          if (!cancelado) setDetalle(d);
        })
        .catch(() => {
          /* se conserva el último detalle */
        });
    };
    tick();
    const id = window.setInterval(tick, 3000);
    return () => {
      cancelado = true;
      window.clearInterval(id);
    };
  }, [equipo.id]);

  const rango = useMemo(() => {
    const ts = samples.map((s) => Date.parse(s.ts)).filter((t) => !Number.isNaN(t));
    if (!ts.length) return null;
    return { desde: Math.min(...ts), hasta: Math.max(...ts) };
  }, [samples]);

  const muestra = useMemo(() => {
    if (!historico || !samples.length) return null;
    const anteriores = samples.filter((s) => Date.parse(s.ts) <= momento!);
    return anteriores.length ? anteriores[anteriores.length - 1] : null;
  }, [historico, samples, momento]);

  /* Metadatos y relaciones estables por equipo (se recalculan al cambiar de lienzo) */
  const metas = useMemo(() => metasDe(equipo.id), [equipo.id]);
  const aristas = useMemo(() => aristasDe(equipo.id), [equipo.id]);
  const paneles = useMemo(() => panelesDe(equipo.id), [equipo.id]);

  if (load === 'loading') return <LoadingBlock label="Abriendo el lienzo…" />;
  if (load === 'error') return <ErrorBlock message={error ?? undefined} onRetry={reload} />;
  if (!eq) {
    return <ErrorBlock title={`Equipo ${equipo.id} no disponible`} message="La API /api/equipment no lo devolvió." onRetry={reload} />;
  }

  const valor = historico ? (muestra?.value ?? eq.value) : eq.value;
  const tsActual = historico ? (muestra?.ts ?? eq.timestamp) : eq.timestamp;
  const senalEquipo = equipo.id === 'caudal-mcc09'
    ? caudalSenal
    : equipo.id === 'presion-mcp09'
      ? presionSenal
      : equipo.id === 'temp-mct09'
        ? temperaturaSenal
        : senal;

  const ctx: CtxLienzo = {
    equipoId: equipo.id,
    eq,
    valor,
    tsActual,
    historico,
    fresco: !stale && !historico,
    online: eq.status === 'ONLINE',
    edad: historico ? timeOnly(momento ?? Date.now()) : formatAge(age),
    age,
    momento,
    detalle,
    enlace: equipo.protocolo,
    senal: senalEquipo,
  };

  const lecturas = lecturasDe(ctx);
  const diag = diagnosticoDe(ctx);
  /* Modo real del selector (solo existe para el módulo de nivel) */
  const modo = equipo.id === 'nivel-mcn09' || equipo.id === 'caudal-mcc09' ? (senalModo(senalEquipo) ?? '—') : '—';
  const chip = historico ? 'historico' : 'vivo';

  /* Estado del lienzo: objeto nuevo en cada render (igual que la tesis) */
  const estado: Estado = {
    resalte: resalteDe(diag),
    agenteTocando: new Set<string>(),
    editando: false,
    tema: 'claro',
    flujo: { activo: !stale && !historico, intensidad: Math.abs(valor) },
    lecturas,
  };

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
            <nav className="lz-migas" aria-label="Ubicación">
              <button type="button" className="lz-miga" onClick={() => onNavigate('lienzo-planta')}>
                Laboratorio
              </button>
              <span>›</span>
              <b>{equipo.nombre}</b>
            </nav>
            <h1>
              {equipo.nombre} · {equipo.codigo}
            </h1>
            <p title={`${equipo.plc} · ${equipo.ip} · ${equipo.protocolo}`}>
              {equipo.plc} · {equipo.ip} · {equipo.protocolo}
            </p>
          </div>
        </div>

        <div className="lz-estados">
          <Pill ok={health === 'ok' ? true : health === 'error' ? false : undefined} txt="API REST" />
          <Pill ok={link === 'connected' ? true : link === 'disconnected' ? false : undefined} txt="SignalR" />
          <Pill ok={samples.length > 0 ? true : undefined} txt="Historial" />
          <Pill ok={eq.status === 'ONLINE'} txt="PLC" />
          <span className="lz-pill lz-modo">{modo}</span>
          <span className="lz-pill lz-ro" title="Ninguna parte del lienzo puede escribir en el PLC">
            <IconLock width="13" height="13" /> Solo lectura
          </span>
        </div>
      </header>

      {historico ? (
        <div className="lz-band">
          Reproduciendo el historial a las <b>{timeOnly(momento ?? Date.now())}</b> · los valores y el diagnóstico
          corresponden a ese momento
        </div>
      ) : null}

      {/* Zona del lienzo: canvas + barra de tiempo pegada abajo (header inferior) */}
      <div className="lz-zona">
        <PanelesCtx.Provider value={{ diag, equipo, momento, chip }}>
          <Ctx.Provider value={estado}>
            <AccCtx.Provider value={ACCIONES}>
              <VistaEquipo equipoId={equipo.id} metas={metas} aristas={aristas} paneles={paneles} />
            </AccCtx.Provider>
          </Ctx.Provider>
        </PanelesCtx.Provider>

        {rango ? <TimeBar momento={momento} desde={rango.desde} hasta={rango.hasta} onCambio={setMomento} /> : null}
      </div>
    </div>
  );
}
