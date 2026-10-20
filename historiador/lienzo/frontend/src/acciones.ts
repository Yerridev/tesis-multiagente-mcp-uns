import { createContext, useContext } from 'react';
import type { Arista } from './types';

export interface Acciones {
  /** El agente consulto estas variables / entidades: pulsa los nodos que las contienen. */
  agenteToca: (nodos: string[]) => void;
  /** El agente obtuvo un diagnostico: resalta su cadena causal en el lienzo. */
  agenteCadena: (aristas: Arista[]) => void;
  /** Ir a un momento del historial (null = en vivo). */
  irA: (momento: string | null) => void;
  nodosDeVariables: (vars: string[]) => string[];
}

export const AccCtx = createContext<Acciones>({
  agenteToca: () => {},
  agenteCadena: () => {},
  irA: () => {},
  nodosDeVariables: () => [],
});

export const useAcciones = () => useContext(AccCtx);
