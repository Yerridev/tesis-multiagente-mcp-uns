import { createContext, useContext } from 'react';

export interface Arista {
  de: string;
  a: string;
}

/** Acciones del lienzo (portadas de acciones.ts de la tesis). */
export interface Acciones {
  /** El agente consultó estas variables/entidades: pulsa los nodos que las contienen. */
  agenteToca: (nodos: string[]) => void;
  /** El agente obtuvo un diagnóstico: resalta su cadena causal en el lienzo. */
  agenteCadena: (aristas: Arista[]) => void;
  /** Ir a un momento del historial (null = en vivo). */
  irA: (momento: number | null) => void;
  nodosDeVariables: (vars: string[]) => string[];
}

export const AccCtx = createContext<Acciones>({
  agenteToca: () => {},
  agenteCadena: () => {},
  irA: () => {},
  nodosDeVariables: () => [],
});

export const useAcciones = () => useContext(AccCtx);
