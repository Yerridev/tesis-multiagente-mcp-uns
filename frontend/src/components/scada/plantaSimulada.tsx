import { useEffect, useState } from 'react';

/* ============================================================
   PLANTA SIMULADA (MODO_PLANTA=simulado en el backend)
   Una sola planta para SCADA, lienzos y agentes: los simuladores Python.
   - El backend dice el modo en GET /api/planta/modo.
   - Las llaves manuales (V1..V7, VF) y los niveles de tanque vienen del simulador
     como valores "sim/V1", "sim/t1_pct", "sim/t1_alto"... de las señales del módulo.
   - Mover una llave = POST /api/sim/llave → MQTT → simulador (solo en planta simulada).
   ============================================================ */

export type ModoPlanta = 'real' | 'simulado';
type Valores = Record<string, { valor?: unknown } | undefined> | undefined;

let cache: ModoPlanta | null = null;
let pendiente: Promise<ModoPlanta> | null = null;

function pedirModo(): Promise<ModoPlanta> {
  if (!pendiente) {
    pendiente = fetch('/api/planta/modo')
      .then((r) => (r.ok ? r.json() : { modo: 'real' }))
      .then((d: { modo?: string }) => (d?.modo === 'simulado' ? 'simulado' : 'real') as ModoPlanta)
      .catch(() => 'real' as ModoPlanta)
      .then((m) => { cache = m; return m; });
  }
  return pendiente;
}

/** 'simulado' cuando el backend corre con MODO_PLANTA=simulado. */
export function usePlantaModo(): ModoPlanta {
  const [modo, setModo] = useState<ModoPlanta>(cache ?? 'real');
  useEffect(() => { let vivo = true; void pedirModo().then((m) => { if (vivo) setModo(m); }); return () => { vivo = false; }; }, []);
  return modo;
}

function val(v: Valores, k: string): unknown { return v?.[k]?.valor; }
function bool(v: Valores, k: string): boolean | null {
  const x = val(v, k);
  if (typeof x === 'boolean') return x;
  if (typeof x === 'number') return x >= 0.5;
  if (x === 'true' || x === 'True') return true;
  if (x === 'false' || x === 'False') return false;
  return null;
}
function num(v: Valores, k: string): number | null {
  const x = val(v, k);
  const n = typeof x === 'number' ? x : typeof x === 'string' ? Number(x) : NaN;
  return Number.isFinite(n) ? n : null;
}

/** Lee del simulador las llaves y los tanques. */
export function leerSim(valores: Valores, llaves: string[]) {
  const valvulas = Object.fromEntries(llaves.map((id) => [id, bool(valores, `sim/${id}`)])) as Record<string, boolean | null>;
  return {
    valvulas,
    t1: num(valores, 'sim/t1_pct'), t2: num(valores, 'sim/t2_pct'),
    t1Alto: bool(valores, 'sim/t1_alto'), t1Bajo: bool(valores, 'sim/t1_bajo'),
    t2Alto: bool(valores, 'sim/t2_alto'), t2Bajo: bool(valores, 'sim/t2_bajo'),
    hay: valores?.['sim/planta'] != null,
  };
}

/** Abre/cierra una llave de la planta simulada. */
export async function moverLlave(modulo: string, id: string, abierta: boolean): Promise<string | null> {
  try {
    const r = await fetch('/api/sim/llave', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ modulo, id, abierta }) });
    if (r.ok) return null;
    const d = await r.json().catch(() => ({}));
    return (d as { error?: string }).error ?? `HTTP ${r.status}`;
  } catch (e) { return (e as Error).message; }
}

export interface Chequeo { id: string; texto: string; ok: boolean }

/** Enclavamientos de arranque de cada módulo (los mismos del simulador del navegador). */
export function chequeosPlanta(
  plcOk: boolean,
  s: ReturnType<typeof leerSim>,
  reglas: { abiertas: string[]; cerradas: string[]; tanques: Array<'t1' | 't2'>; soloBajo?: boolean },
): Chequeo[] {
  const lista: Chequeo[] = [{ id: 'plc', texto: 'PLC conectado', ok: plcOk }];
  for (const t of reglas.tanques) {
    const alto = t === 't1' ? s.t1Alto : s.t2Alto, bajo = t === 't1' ? s.t1Bajo : s.t2Bajo;
    lista.push(reglas.soloBajo
      ? { id: t, texto: `${t.toUpperCase()} sin nivel bajo`, ok: bajo === false }
      : { id: t, texto: `${t.toUpperCase()} sin nivel alto ni nivel bajo`, ok: alto === false && bajo === false });
  }
  if (reglas.abiertas.length) lista.push({ id: 'ab', texto: `${reglas.abiertas.join(' y ')} abierta${reglas.abiertas.length > 1 ? 's' : ''}`, ok: reglas.abiertas.every((v) => s.valvulas[v] === true) });
  if (reglas.cerradas.length) lista.push({ id: 'ce', texto: `${reglas.cerradas.join(', ')} cerradas`, ok: reglas.cerradas.every((v) => s.valvulas[v] === false) });
  return lista;
}

/** Caja de enclavamientos de la planta simulada (mismo estilo que el PLC virtual del navegador). */
export function CajaPlanta({ chequeos, aviso }: { chequeos: Chequeo[]; aviso?: string | null }) {
  const listo = chequeos.every((c) => c.ok);
  return (
    <div className="plcv">
      <div className="plcv-head">
        <span className={`plcv-dot ${chequeos[0]?.ok ? 'conectado' : ''}`} />
        <b>Planta simulada · enclavamientos</b>
      </div>
      <ul className="plcv-checks">
        {chequeos.map((c) => <li key={c.id} className={c.ok ? 'ok' : ''}>{c.ok ? '✔' : '✖'} {c.texto}</li>)}
      </ul>
      <small>{aviso ?? (listo ? 'Todo listo: puedes dar Iniciar' : 'Mueve las llaves en el mímico hasta cumplir')}</small>
    </div>
  );
}
