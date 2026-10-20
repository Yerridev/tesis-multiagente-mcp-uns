import { createContext, useContext } from 'react';
import type { Diagnostico, Enlace, Grafo, Valor } from './types';

export interface Resalte {
  aristas: Set<string>; // "de|a"
  nodos: Set<string>;
  fuente: 'diagnostico' | 'agente' | null;
}

export interface Estado {
  grafo: Grafo | null;
  valores: Record<string, Valor>;
  enlace: Enlace | null;
  diag: Diagnostico | null;
  momento: string | null; // null = en vivo
  resalte: Resalte;
  agenteTocando: Set<string>; // nodos que el agente esta consultando
  editando: boolean;
  tema: 'oscuro' | 'claro';
}

export const vacio: Resalte = { aristas: new Set(), nodos: new Set(), fuente: null };

export const Ctx = createContext<Estado>({
  grafo: null,
  valores: {},
  enlace: null,
  diag: null,
  momento: null,
  resalte: vacio,
  agenteTocando: new Set(),
  editando: false,
  tema: 'oscuro',
});

export const useEstado = () => useContext(Ctx);

export function valorNum(valores: Record<string, Valor>, v: string): number | null {
  const x = valores[v]?.valor;
  if (x === null || x === undefined) return null;
  if (typeof x === 'boolean') return x ? 1 : 0;
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

export function resalteDe(diag: Diagnostico | null): Resalte {
  if (!diag) return vacio;
  const aristas = new Set<string>();
  const nodos = new Set<string>();
  const add = (l?: { de: string; a: string }[]) =>
    (l ?? []).forEach((x) => {
      aristas.add(`${x.de}|${x.a}`);
      nodos.add(x.de);
      nodos.add(x.a);
    });
  add(diag.aristas_causales);
  diag.hallazgos_secundarios.forEach((h) => add(h.aristas));
  return { aristas, nodos, fuente: 'diagnostico' };
}

/** Severidad del diagnostico para el color (ISA-101: color solo para lo anormal). */
export function severidad(d?: string | null): 'normal' | 'aviso' | 'alarma' | 'info' {
  switch (d) {
    case 'REGULANDO':
      return 'normal';
    case 'SATURADO_FUERA_DE_CAPACIDAD':
    case 'SIN_DATOS':
      return 'alarma';
    case 'BOMBA_DETENIDA':
    case 'DESVIACION_SIN_SATURAR':
    case 'SATURADO_EN_MINIMO':
      return 'aviso';
    default:
      return 'info';
  }
}
