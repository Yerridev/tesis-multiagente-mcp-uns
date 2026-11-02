export type Sev = 'normal' | 'activo' | 'aviso' | 'alarma' | 'inactivo' | 'info';

/** Nodo de equipo (forma portada de NodoGrafo + Lectura de la tesis). */
export interface LienzoNode {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  tipo: string;
  nombre: string;
  icono: React.ReactNode;
  estado?: { texto: string; sev: Sev };
  principal?: { valor: string; unidad: string };
  barra?: { pct: number; sev: Sev; etiqueta: string };
  filas: { k: string; v: string; u?: string }[];
}

/** Relación del grafo (Relacion de la tesis). */
export interface LienzoEdge {
  de: string;
  a: string;
  rel: string;
  nota?: string;
  flujo?: boolean;
}

/** Contenido vivo de un nodo (Lectura de la tesis): estado, valor, barra y filas. */
export interface Lectura {
  estado?: { texto: string; sev: Sev };
  principal?: { valor: string; unidad: string };
  barra?: { pct: number; sev: Sev; etiqueta: string };
  filas: { k: string; v: string; u?: string }[];
}

/** Metadatos estáticos de un nodo (tipo, nombre, icono y posición del grafo). */
export interface MetaNodo {
  id: string;
  x: number;
  y: number;
  w: number;
  tipo: string;
  nombre: string;
  icono: React.ReactNode;
}
