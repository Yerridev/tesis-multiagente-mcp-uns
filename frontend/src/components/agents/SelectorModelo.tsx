import { useEffect, useRef, useState } from 'react';
import type { AgentStatus } from '../../types';

/* ============================================================
   Selector de modelo junto a "Enviar" (chat de Agentes y lienzos).
   La lista la da el backend (/api/agent/status → models): el navegador
   solo puede elegir entre esos. La elección se recuerda en este navegador.
   ============================================================ */

export type ModeloIa = { id: string; nombre: string; gratis: boolean };
const CLAVE = 'mcp.modeloIa';

function leer(): string | null { try { return localStorage.getItem(CLAVE); } catch { return null; } }
function guardar(v: string) { try { localStorage.setItem(CLAVE, v); } catch { /* sin almacenamiento: solo en memoria */ } }

/** Modelo elegido (compartido entre chats del mismo navegador). */
export function useModeloElegido(status: AgentStatus | null) {
  const modelos: ModeloIa[] = status?.models ?? (status?.model ? [{ id: status.model, nombre: status.model, gratis: false }] : []);
  const [id, setId] = useState<string | null>(leer);
  const valido = id && modelos.some((m) => m.id === id) ? id : status?.model ?? modelos[0]?.id ?? null;
  const elegir = (v: string) => { setId(v); guardar(v); };
  return { modelos, modelo: valido, actual: modelos.find((m) => m.id === valido) ?? null, elegir };
}

export function SelectorModelo({ modelos, valor, onElegir, disabled }: { modelos: ModeloIa[]; valor: string | null; onElegir: (id: string) => void; disabled?: boolean }) {
  const [abierto, setAbierto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setAbierto(false); };
    document.addEventListener('mousedown', fuera); window.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', fuera); window.removeEventListener('keydown', esc); };
  }, [abierto]);
  if (!modelos.length) return null;
  const actual = modelos.find((m) => m.id === valor) ?? modelos[0];
  return (
    <div className="sm-wrap nodrag nowheel" ref={ref}>
      <button type="button" className="sm-btn" disabled={disabled} onClick={() => setAbierto((v) => !v)} title={`Modelo: ${actual.id}`} aria-haspopup="listbox" aria-expanded={abierto}>
        <span className="sm-nombre">{actual.nombre}</span>
        <span className="sm-flecha" aria-hidden>▾</span>
      </button>
      {abierto && (
        <div className="sm-menu" role="listbox" aria-label="Elegir modelo">
          <div className="sm-cab">Modelo de IA</div>
          {modelos.map((m) => (
            <button key={m.id} type="button" role="option" aria-selected={m.id === actual.id}
              className={`sm-op${m.id === actual.id ? ' activo' : ''}`} onClick={() => { onElegir(m.id); setAbierto(false); }}>
              <span className="sm-op-txt"><b>{m.nombre}</b><small>{m.id}</small></span>
              {m.gratis ? <span className="sm-gratis">Gratis</span> : <span className="sm-pago">Créditos</span>}
              <span className="sm-check" aria-hidden>{m.id === actual.id ? '✓' : ''}</span>
            </button>
          ))}
          <div className="sm-pie">Gratis: límite diario de consultas compartido. Créditos: consume saldo de OpenRouter.</div>
        </div>
      )}
    </div>
  );
}
