import { createContext, useContext } from 'react';
import type { Diagnostico } from '../components/lienzo/panels/DiagnosticoPanel';
import type { Lectura } from './tipos';

/** Resalte de la cadena causal (portado de ctx.tsx de la tesis). */
export interface Resalte {
  aristas: Set<string>; // "de|a"
  nodos: Set<string>;
  fuente: 'diagnostico' | 'agente' | null;
}

export interface Estado {
  /** Cadena causal que se resalta en el lienzo (del diagnóstico o del agente). */
  resalte: Resalte;
  /** Nodos que el agente está consultando. */
  agenteTocando: Set<string>;
  /** Modo edición del knowledge graph: no se porta, siempre false. */
  editando: boolean;
  tema: 'claro';
  /** Flujo de proceso animado (partículas) cuando hay datos en vivo. */
  flujo: { activo: boolean; intensidad: number };
  /** Enlace con el PLC caído: relaciones en gris, sin resalte ni partículas. */
  congelado?: boolean;
  /**
   * Lectura viva de cada nodo (adapta `valores` de la tesis): los nodos son
   * estáticos y los datos actualizados llegan por contexto.
   */
  lecturas: Record<string, Lectura>;
}

export const vacio: Resalte = { aristas: new Set(), nodos: new Set(), fuente: null };

export const Ctx = createContext<Estado>({
  resalte: vacio,
  agenteTocando: new Set(),
  editando: false,
  tema: 'claro',
  flujo: { activo: false, intensidad: 0 },
  lecturas: {},
});

export const useEstado = () => useContext(Ctx);

/** Construye el resalte a partir de la cadena causal del diagnóstico. */
export function resalteDe(diag: Diagnostico | null): Resalte {
  if (!diag || !diag.cadena.length) return vacio;
  const aristas = new Set<string>();
  const nodos = new Set<string>();
  diag.cadena.forEach((x) => {
    aristas.add(`${x.de}|${x.a}`);
    nodos.add(x.de);
    nodos.add(x.a);
  });
  return { aristas, nodos, fuente: 'diagnostico' };
}
