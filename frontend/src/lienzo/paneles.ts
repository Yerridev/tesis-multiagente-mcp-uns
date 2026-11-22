import { createContext, useContext } from 'react';
import type { Diagnostico } from '../components/lienzo/panels/DiagnosticoPanel';
import type { EquipoLienzo } from '../pages/lienzo/lienzoData';

/** Los 4 paneles del lienzo (Diagnóstico, Agente, Tendencia, UNS). */
export type TipoPanel = 'diagnostico' | 'agente' | 'tendencia' | 'uns';

/**
 * Datos que los paneles leen cuando viven DENTRO del canvas (como en la tesis):
 * se publican en LienzoPage y los consume PanelNode (nodo ReactFlow).
 */
export interface DatosPaneles {
  diag: Diagnostico;
  equipo: EquipoLienzo;
  momento: number | null;
  chip: 'vivo' | 'historico';
}

export const PanelesCtx = createContext<DatosPaneles | null>(null);

export function usePaneles(): DatosPaneles {
  const ctx = useContext(PanelesCtx);
  if (!ctx) throw new Error('usePaneles se usó fuera de PanelesCtx.Provider');
  return ctx;
}
