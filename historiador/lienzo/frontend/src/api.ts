import type { Diagnostico, EventoLinea, Grafo, Salud, Valor, Enlace } from './types';

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let detalle = `${r.status}`;
    try {
      const b = await r.json();
      detalle = b.detail ?? JSON.stringify(b);
    } catch {
      /* sin cuerpo */
    }
    throw new Error(detalle);
  }
  return r.json() as Promise<T>;
}

const q = (o: Record<string, string | number | undefined | null>) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');

export const api = {
  salud: () => j<Salud>('/api/salud'),
  grafo: () => j<Grafo>('/api/grafo'),
  guardarGrafo: (g: Partial<Grafo>) =>
    j<{ ok: boolean; respaldo: string }>('/api/grafo', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(g),
    }),
  estado: (momento?: string) =>
    j<{ momento: string; en_vivo: boolean; valores: Record<string, Valor>; enlace: Enlace | null }>(
      `/api/estado?${q({ momento })}`,
    ),
  diagnostico: (momento?: string) => j<Diagnostico>(`/api/diagnostico?${q({ momento })}`),
  rango: () => j<{ desde: string | null; hasta: string | null }>('/api/rango'),
  eventos: (inicio: string, fin: string) => j<EventoLinea[]>(`/api/eventos?${q({ inicio, fin })}`),
  historial: (variables: string[], inicio: string, fin: string, puntos = 300) =>
    j<{ inicio: string; fin: string; paso_s: number; series: Record<string, [string, number][]> }>(
      `/api/historial?${q({ variables: variables.join(','), inicio, fin, puntos })}`,
    ),
  variables: () =>
    j<{ variables: { variable: string; unidad: string | null; descripcion: string | null; direccion: string | null }[] }>(
      '/api/variables',
    ),
};

/** Lee un stream SSE de POST /api/agente y entrega cada evento JSON. */
export async function conversar(
  mensajes: { role: 'user' | 'assistant'; content: string }[],
  alEvento: (ev: Record<string, unknown>) => void,
  senal?: AbortSignal,
) {
  const r = await fetch('/api/agente', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mensajes }),
    signal: senal,
  });
  if (!r.ok || !r.body) {
    let detalle = `${r.status}`;
    try {
      detalle = (await r.json()).detail ?? detalle;
    } catch {
      /* nada */
    }
    alEvento({ tipo: 'error', detalle });
    return;
  }
  const lector = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await lector.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const bloque = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const linea = bloque.split('\n').find((l) => l.startsWith('data: '));
      if (linea) {
        try {
          alEvento(JSON.parse(linea.slice(6)));
        } catch {
          /* bloque incompleto */
        }
      }
    }
  }
}

export const fmtHora = (iso?: string | null) => (iso ? iso.slice(11, 19) : '--:--:--');

export function fmtNum(v: unknown, dec = 1): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'Sí' : 'No';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString('es-PE', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

/** Hora local de Lima (UTC-5) en ISO sin zona, para los endpoints. */
export function isoLima(ms: number): string {
  return new Date(ms - 5 * 3600e3).toISOString().slice(0, 19) + '-05:00';
}
