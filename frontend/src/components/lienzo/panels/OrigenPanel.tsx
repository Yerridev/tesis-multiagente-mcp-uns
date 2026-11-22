import { useMemo, useState } from 'react';
import { usePlant } from '../../../context/PlantContext';
import { formatAge, num, timeOnly } from '../../../utils/format';

interface Props {
  /** Momento histórico (epoch ms) o null = en vivo */
  momento: number | null;
  /** Módulo cuyas variables muestra el panel (por defecto, todas) */
  solo?: string;
}

interface Hoja {
  nombre: string;
  valor: string;
  unidad?: string;
  t?: string;
}

/**
 * Origen de datos (equivalente del "Unified Namespace" de la tesis):
 * lista agrupada y plegable de las variables que alimentan el lienzo.
 */
export function OrigenPanel({ momento, solo }: Props) {
  const { equipment, historyFor, now } = usePlant();
  const [abiertas, setAbiertas] = useState<Record<string, boolean>>({});

  const grupos = useMemo(() => {
    return equipment
      .filter((eq) => !solo || eq.id === solo)
      .map((eq) => {
      const hojas: Hoja[] = [];
      const muestras = historyFor(eq.id);
      const hist = momento === null ? null : [...muestras].reverse().find((s) => Date.parse(s.ts) <= momento) ?? null;

      const conSigna = eq.setpoint > 0;
      if (hist) {
        const ts = timeOnly(hist.ts);
        hojas.push({ nombre: eq.variable.toLowerCase(), valor: num(hist.value, 2), unidad: eq.unit, t: ts });
        hojas.push({ nombre: 'consigna', valor: conSigna ? num(eq.setpoint, 2) : 'Sin datos', unidad: conSigna ? eq.unit : undefined, t: ts });
        hojas.push({ nombre: 'desviación', valor: conSigna ? num(hist.value - eq.setpoint, 2) : 'Sin datos', unidad: conSigna ? eq.unit : undefined, t: ts });
        hojas.push({ nombre: 'dispositivo', valor: 'Sin histórico', t: ts });
      } else if (momento !== null) {
        hojas.push({ nombre: eq.variable.toLowerCase(), valor: 'Sin muestra', t: '—' });
      } else if (eq.status !== 'ONLINE') {
        /* sin comunicación: no se presentan valores */
        hojas.push({ nombre: eq.variable.toLowerCase(), valor: 'Sin datos', t: '—' });
        hojas.push({ nombre: 'consigna', valor: conSigna ? num(eq.setpoint, 2) : 'Sin datos', unidad: conSigna ? eq.unit : undefined, t: '—' });
        hojas.push({ nombre: 'estado', valor: eq.status, t: timeOnly(eq.timestamp) });
      } else {
        const ts = timeOnly(eq.timestamp);
        hojas.push({ nombre: eq.variable.toLowerCase(), valor: num(eq.value, 2), unidad: eq.unit, t: ts });
        hojas.push({ nombre: 'consigna', valor: conSigna ? num(eq.setpoint, 2) : 'Sin datos', unidad: conSigna ? eq.unit : undefined, t: ts });
        hojas.push({ nombre: 'desviación', valor: conSigna ? num(eq.deviation, 2) : 'Sin datos', unidad: conSigna ? eq.unit : undefined, t: ts });
        hojas.push({ nombre: 'estado', valor: eq.status, t: ts });
        hojas.push({ nombre: 'antigüedad', valor: formatAge(ageOf(now, eq.timestamp)), t: ts });
      }
      return { id: eq.id, nombre: `${eq.variable} · ${eq.id}`, hojas };
    });
  }, [equipment, historyFor, momento, now, solo]);

  const base = momento === null ? 'GET /api/equipment · /api/stream' : `/api/history · momento ${timeOnly(momento)}`;

  return (
    <div className="lz-uns">
      <div className="lz-uns-base" title={base}>
        backend <b>{momento === null ? ' · SSE en vivo' : ' · historial'}</b>
      </div>
      {grupos.map((grupo) => {
        const abierta = abiertas[grupo.id] ?? true;
        return (
          <div className="lz-uns-grupo" key={grupo.id}>
            <button
              type="button"
              className="lz-uns-cab"
              onClick={() => setAbiertas((prev) => ({ ...prev, [grupo.id]: !abierta }))}
            >
              <span className={`lz-chev${abierta ? ' abierto' : ''}`}>▸</span>
              {grupo.nombre}
              <small>{grupo.hojas.length}</small>
            </button>
            {abierta
              ? grupo.hojas.map((hoja, index) => (
                  <div className="lz-uns-hoja" key={`${grupo.id}-${hoja.nombre}-${index}`}>
                    <span className="lz-uns-nombre">{hoja.nombre}</span>
                    <span className={`lz-uns-val${/sin |—/.test(hoja.valor) ? ' nodata' : ''}`}>
                      {hoja.valor}
                      {hoja.unidad ? <small> {hoja.unidad}</small> : null}
                    </span>
                    <span className="lz-uns-t">{hoja.t ?? ''}</span>
                  </div>
                ))
              : null}
          </div>
        );
      })}
    </div>
  );
}

function ageOf(now: number, iso: string): number {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? 0 : Math.max(0, Math.round((now - t) / 1000));
}
