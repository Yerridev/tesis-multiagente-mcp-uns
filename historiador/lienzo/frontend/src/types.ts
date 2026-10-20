export type TipoNodo = 'equipo' | 'sensor' | 'actuador' | 'control' | 'mando' | 'proteccion' | 'proceso';

export interface NodoGrafo {
  tipo: TipoNodo;
  nombre: string;
  variables: string[];
}

export interface Relacion {
  de: string;
  rel: string;
  a: string;
  nota?: string;
}

export interface Grafo {
  modelo: string;
  version?: string;
  nodos: Record<string, NodoGrafo>;
  relaciones: Relacion[];
  layout?: Record<string, [number, number]>;
  capacidad_observada?: Record<string, unknown>;
}

export interface Valor {
  valor: number | boolean | null;
  unidad?: string | null;
  t?: string | null;
}

export interface Enlace {
  datos_en_vivo: boolean;
  conector_edge: string | null;
  conexion_plc: string | null;
  ultimo_latido: string | null;
  segundos_desde_latido: number | null;
  motivos: string[];
}

export interface Arista {
  de: string;
  a: string;
  rel: string;
}

export interface Hallazgo {
  hallazgo: string;
  detalle: string;
  cadena?: string[];
  aristas?: Arista[];
}

export interface Diagnostico {
  consultado: string;
  momento_evaluado: string;
  modo: string;
  evidencia: Record<string, number | null>;
  diagnostico: string;
  explicacion: string;
  cadena_causal: string[];
  aristas_causales?: Arista[];
  hallazgos_secundarios: Hallazgo[];
  recomendacion: string;
}

export interface Salud {
  db: boolean;
  mqtt: boolean;
  agente: boolean;
  modelo: string;
  solo_lectura: boolean;
}

export interface EventoLinea {
  variable: string;
  t: string;
  valor: number;
}

export type Fuente = 'diagnostico' | 'agente';
