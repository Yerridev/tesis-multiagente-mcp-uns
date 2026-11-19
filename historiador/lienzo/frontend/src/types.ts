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
  proveedor?: string;
  solo_lectura: boolean;
  equipos_cargados?: string[];
}

/* ---------- registro de equipos (mcp_servidor/conocimiento/equipos.json) */
export interface VarCfg {
  variable: string;
  nombre: string;
  unidad: string;
  decimales?: number;
  min?: number;
  max?: number;
  aviso?: number;
  alarma?: number;
}

export interface SerieCfg {
  v: string;
  nombre: string;
  eje: number;
  paso?: boolean;
  color?: string;
  grueso?: boolean;
}

export interface EquipoCfg {
  id: string;
  alias: string;
  nombre: string;
  codigo: string;
  proceso: string;
  fabricante?: string;
  plc: string;
  ip: string;
  protocolo: string;
  uns_base: string;
  prefijo_db: string;
  diagnostico: string;
  grafo: string;
  disponible?: boolean;
  principal: VarCfg;
  secundario?: VarCfg;
  marcha: string;
  velocidad?: { variable: string; factor_pct: number };
  flujo?: { variable: string; factor: number };
  tendencia: {
    ejes: { nombre: string; min?: number; max?: number }[];
    series: SerieCfg[];
    lineas?: { eje: number; valor: number; nombre: string }[];
  };
  kpis: { k: string; n: string; u: string; d?: number }[];
  eventos: Record<string, [string, string, string, string]>;
  sugerencias: string[];
}

export interface Organizacion {
  campus?: string;
  area?: string;
  aula?: string;
  uns_raiz?: string;
}

export interface ResumenEquipo {
  id: string;
  disponible?: boolean;
  enlace?: Enlace | null;
  valores?: Record<string, Valor>;
  diagnostico?: { diagnostico: string; explicacion: string; recomendacion: string };
  spark?: [string, number][];
  error?: string;
}

export interface EventoLinea {
  variable: string;
  t: string;
  valor: number;
}

export type Fuente = 'diagnostico' | 'agente';
