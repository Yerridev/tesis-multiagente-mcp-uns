import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { CaudalSenales, ControlOrden, Equipment, HistorySample, LinkState, LoadState, NivelSenales, PresionSenales, TemperaturaSenales } from '../types';
import { api } from '../services/api';
import { listarOrdenes } from '../services/control';
import { createStream } from '../services/stream';
import { valorMedible } from '../utils/format';

const HISTORY_LIMIT = 600;
const HEALTH_MS = 30000;

interface PlantContextValue {
  equipment: Equipment[];
  byId: Record<string, Equipment | undefined>;
  history: HistorySample[];
  historyFor: (id: string) => HistorySample[];
  link: LinkState;
  load: LoadState;
  error: string | null;
  health: 'checking' | 'ok' | 'error';
  now: number;
  lastUpdate: string | null;
  /** Señales reales del módulo de nivel (MQTT/UNS). */
  senal: NivelSenales | null;
  caudalSenal: CaudalSenales | null;
  presionSenal: PresionSenales | null;
  temperaturaSenal: TemperaturaSenales | null;
  /** Últimas órdenes de control (SSE controlResultado + REST). */
  controlOrdenes: ControlOrden[];
  /** Recarga las órdenes desde la API (tras un envío y al montar). */
  controlRecargar: () => void;
  reload: () => void;
}

const PlantContext = createContext<PlantContextValue | null>(null);

export function PlantProvider({ children }: { children: ReactNode }) {
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [history, setHistory] = useState<HistorySample[]>([]);
  const [link, setLink] = useState<LinkState>('connecting');
  const [load, setLoad] = useState<LoadState>('loading');
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<'checking' | 'ok' | 'error'>('checking');
  const [now, setNow] = useState(() => Date.now());
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [senal, setSenal] = useState<NivelSenales | null>(null);
  const [caudalSenal, setCaudalSenal] = useState<CaudalSenales | null>(null);
  const [presionSenal, setPresionSenal] = useState<PresionSenales | null>(null);
  const [temperaturaSenal, setTemperaturaSenal] = useState<TemperaturaSenales | null>(null);
  const [controlOrdenes, setControlOrdenes] = useState<ControlOrden[]>([]);
  const [reloadToken, setReloadToken] = useState(0);

  const lastTs = useRef<Record<string, string>>({});
  const stream = useRef<EventSource | null>(null);

  /* reloj compartido (antigüedad de los datos) */
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  /* carga inicial: REST (estado + calentamiento del historial) */
  useEffect(() => {
    let cancelled = false;
    setLoad('loading');
    setError(null);
    Promise.all([api.equipment(), api.history(undefined, HISTORY_LIMIT)])
      .then(([items, samples]) => {
        if (cancelled) return;
        setEquipment(items);
        setHistory(samples);
        for (const s of samples) { const t = Date.parse(s.ts); if (Number.isFinite(t)) lastTs.current[s.id] = String(Math.max(t, Number(lastTs.current[s.id] ?? 0))); }
        setLastUpdate(
          items.reduce<string | null>((max, i) => (!max || i.timestamp > max ? i.timestamp : max), null),
        );
        setLoad('ready');
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setLoad('error');
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  /* canal SSE · telemetría en vivo */
  useEffect(() => {
    const source = createStream({
      telemetry: (datos) => {
        const items = datos as Equipment[];
        if (!Array.isArray(items)) return;
        /* Fusionar en vez de reemplazar: si un paquete llega sin algún equipo (p. ej. PLC apagado),
           se conserva el último conocido y su SCADA no desaparece de la pantalla. */
        setEquipment((prev) => {
          const nuevos = new Map(items.map((i) => [i.id, i]));
          const fusion = prev.map((p) => nuevos.get(p.id) ?? p);
          for (const i of items) if (!prev.some((p) => p.id === i.id)) fusion.push(i);
          return fusion;
        });
        setHistory((prev) => {
          const next = prev.slice();
          for (const item of items) {
            /* Se compara la HORA (no el texto ISO): distintos offsets o decimales
               hacían que '…T20:10' (UTC) pareciera mayor que '…T15:11-05:00' y la
               tendencia dejaba de avanzar hasta refrescar con F5. */
            const t = Date.parse(item.timestamp);
            const seen = lastTs.current[item.id];
            if (!Number.isFinite(t)) continue;
            if (seen !== undefined && t <= Number(seen)) continue;
            lastTs.current[item.id] = String(t);
            /* Un dato no medible (sensor fuera de rango) NO entra al historial: meter un 0
               o un valor de relleno pintaría una curva plana que parece una medida real. */
            if (!valorMedible(item.calidad) || item.value == null) continue;
            next.push({
              id: item.id,
              variable: item.variable,
              unit: item.unit,
              value: item.value,
              ts: item.timestamp,
            });
          }
          const total: Record<string, number> = {};
          for (const s of next) total[s.id] = (total[s.id] ?? 0) + 1;
          const seenCount: Record<string, number> = {};
          return next.filter((s) => {
            seenCount[s.id] = (seenCount[s.id] ?? 0) + 1;
            return seenCount[s.id] > (total[s.id] ?? 0) - HISTORY_LIMIT;
          });
        });
        setLastUpdate(items.reduce<string | null>((max, i) => (!max || i.timestamp > max ? i.timestamp : max), null));
      },

      nivelSenales: (datos) => setSenal(datos as NivelSenales),
      caudalSenales: (datos) => setCaudalSenal(datos as CaudalSenales),
      presionSenales: (datos) => setPresionSenal(datos as PresionSenales),
      temperaturaSenales: (datos) => setTemperaturaSenal(datos as TemperaturaSenales),

      controlResultado: (datos) => {
        const orden = datos as ControlOrden;
        if (!orden || typeof orden.id !== 'string') return;
        setControlOrdenes((prev) => [orden, ...prev.filter((o) => o.id !== orden.id)].slice(0, 8));
      },
      temperaturaControlResultado: (datos) => {
        const orden = datos as ControlOrden;
        if (!orden || typeof orden.id !== 'string') return;
        setControlOrdenes((prev) => [orden, ...prev.filter((o) => o.id !== orden.id)].slice(0, 8));
      },
    });
    stream.current = source;

    source.onopen = () => setLink('connected');
    /* EventSource reconecta solo: mientras intenta, el canal está 'reconectando'. */
    source.onerror = () => setLink('reconnecting');

    return () => {
      source.close();
      stream.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelado = false;
    api.caudalSenales().then((s) => { if (!cancelado) setCaudalSenal(s); }).catch(() => {});
    api.presionSenales().then((s) => { if (!cancelado) setPresionSenal(s); }).catch(() => {});
    api.temperaturaSenales().then((s) => { if (!cancelado) setTemperaturaSenal(s); }).catch(() => {});
    return () => { cancelado = true; };
  }, []);

  /* señales reales del módulo de nivel (carga inicial; luego llegan por el canal SSE) */
  useEffect(() => {
    let cancelado = false;
    api
      .nivelSenales()
      .then((s) => {
        if (!cancelado) setSenal(s);
      })
      .catch(() => {
        /* sin señales: la interfaz muestra SIN DATOS */
      });
    return () => {
      cancelado = true;
    };
  }, []);

  /* salud de la API REST */
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      api
        .health()
        .then(() => !cancelled && setHealth('ok'))
        .catch(() => !cancelled && setHealth('error'));
    };
    check();
    const id = window.setInterval(check, HEALTH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const reload = useCallback(() => setReloadToken((t) => t + 1), []);

  const controlRecargar = useCallback(() => {
    listarOrdenes()
      .then((r) => {
        if (r.ok && Array.isArray(r.datos)) setControlOrdenes(r.datos);
      })
      .catch(() => {
        /* sin órdenes: se siguen viendo las llegadas por el canal */
      });
  }, []);

  const byId = useMemo(() => {
    const map: Record<string, Equipment | undefined> = {};
    for (const item of equipment) map[item.id] = item;
    return map;
  }, [equipment]);

  const historyFor = useCallback(
    (id: string) => history.filter((s) => s.id === id),
    [history],
  );

  const value: PlantContextValue = {
    equipment,
    byId,
    history,
    historyFor,
    link,
    load,
    error,
    health,
    now,
    lastUpdate,
    senal,
    caudalSenal,
    presionSenal,
    temperaturaSenal,
    controlOrdenes,
    controlRecargar,
    reload,
  };

  return <PlantContext.Provider value={value}>{children}</PlantContext.Provider>;
}

export function usePlant(): PlantContextValue {
  const ctx = useContext(PlantContext);
  if (!ctx) throw new Error('usePlant debe usarse dentro de <PlantProvider>');
  return ctx;
}
