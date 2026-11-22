import { useCallback, useEffect, useState } from 'react';
import { useNodesState, type Node } from '@xyflow/react';

/**
 * Nodos estables como en los lienzos: React Flow es dueño de los nodos (useNodesState),
 * los datos en vivo solo actualizan `data` sin tocar la posición, y las posiciones
 * arrastradas se guardan en localStorage por diagrama.
 */
export function useNodosEstables<T extends Record<string, unknown>>(clave: string, base: Node<T>[]) {
  const leer = (): Record<string, { x: number; y: number }> => {
    try { return JSON.parse(localStorage.getItem(clave) ?? '{}'); } catch { return {}; }
  };
  // primer render ya con los nodos en su posicion final (fitView encuadra una sola vez, sin saltos)
  const [inicial] = useState(() => { const g = leer(); return base.map((n) => ({ ...n, position: g[n.id] ?? n.position })); });
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<T>>(inicial);

  useEffect(() => {
    const guardadas = leer();
    setNodes((prev) => {
      const actuales = new Map(prev.map((n) => [n.id, n]));
      return base.map((n) => {
        const ya = actuales.get(n.id);
        if (ya?.dragging) return { ...ya, data: n.data };             // se esta arrastrando: no tocar
        // posicion: la que el usuario dejo (guardada) o la predeterminada del diseño
        return { ...(ya ?? n), data: n.data, position: guardadas[n.id] ?? n.position };
      });
    });
  }, [base, clave, setNodes]);

  const onNodeDragStop = useCallback((_e: unknown, _n: Node<T>, arrastrados: Node<T>[]) => {
    try {
      const g = JSON.parse(localStorage.getItem(clave) ?? '{}');
      for (const n of arrastrados ?? []) g[n.id] = n.position;
      localStorage.setItem(clave, JSON.stringify(g));
    } catch { /* sin almacenamiento */ }
  }, [clave]);

  const reiniciar = useCallback(() => {
    try { localStorage.removeItem(clave); } catch { /* sin almacenamiento */ }
    setNodes(base.map((n) => ({ ...n })));
  }, [base, clave, setNodes]);

  return { nodes, onNodesChange, onNodeDragStop, reiniciar };
}
