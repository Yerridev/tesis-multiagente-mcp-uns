/**
 * Re-encuadra el mímico SOLO cuando su contenedor cambia de tamaño de verdad
 * y el usuario todavía no ha hecho zoom ni movido la vista.
 * Así, si agrandas/achicas o arrastras, la vista se queda donde la dejaste
 * (antes los datos en vivo hacían que volviera sola al encuadre inicial).
 * El botón ⛶ de los controles sigue re-encuadrando cuando quieras.
 */
export function observarEncuadre(el: HTMLElement, encuadrar: () => void): ResizeObserver {
  let ancho = 0;
  let alto = 0;
  let tocado = false;
  const marcar = () => { tocado = true; };
  el.addEventListener('wheel', marcar, { passive: true });
  el.addEventListener('pointerdown', (e) => {
    // clic en los botones de zoom/arrastre del lienzo = el usuario controla la vista
    if (!(e.target as HTMLElement).closest('.react-flow__controls-fitview')) marcar();
    else tocado = false;  // ⛶ vuelve al encuadre automático
  });
  const ro = new ResizeObserver(([entrada]) => {
    const { width, height } = entrada.contentRect;
    const cambio = Math.abs(width - ancho) > 2 || Math.abs(height - alto) > 2;
    ancho = width;
    alto = height;
    if (cambio && !tocado && width > 0 && height > 0) encuadrar();
  });
  ro.observe(el);
  return ro;
}

/* ────────────────────────────────────────────────────────────────────────────
   Medidas estables de los nodos.
   Los mímicos recalculan sus nodos con cada dato en vivo. Sin `onNodesChange`,
   React Flow pierde el tamaño medido de cada nodo cuando el objeto cambia y los
   deja con `visibility: hidden` → el mímico "desaparece" a los pocos segundos.
   Este hook guarda las medidas y se las devuelve a cada nodo nuevo.
   ──────────────────────────────────────────────────────────────────────────── */
import { useCallback, useMemo, useState } from 'react';
import type { Node, NodeChange } from '@xyflow/react';

type Medida = { width: number; height: number };

export function useMedidasEstables(nodes: Node[]): { nodes: Node[]; onNodesChange: (c: NodeChange[]) => void } {
  const [medidas, setMedidas] = useState<Record<string, Medida>>({});
  const onNodesChange = useCallback((cambios: NodeChange[]) => {
    const nuevas: Record<string, Medida> = {};
    for (const c of cambios) {
      if (c.type === 'dimensions' && c.dimensions) nuevas[c.id] = { width: c.dimensions.width, height: c.dimensions.height };
    }
    if (Object.keys(nuevas).length) {
      setMedidas((prev) => {
        const igual = Object.entries(nuevas).every(([id, m]) => prev[id] && prev[id].width === m.width && prev[id].height === m.height);
        return igual ? prev : { ...prev, ...nuevas };
      });
    }
  }, []);
  const conMedidas = useMemo(() => nodes.map((n) => (medidas[n.id] ? { ...n, measured: medidas[n.id] } : n)), [nodes, medidas]);
  return { nodes: conMedidas, onNodesChange };
}
