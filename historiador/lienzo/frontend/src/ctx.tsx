import { createContext, useContext } from 'react';
import type { Diagnostico, Enlace, EquipoCfg, Grafo, Valor } from './types';

export interface Resalte {
  aristas: Set<string>; // "de|a"
  nodos: Set<string>;
  fuente: 'diagnostico' | 'agente' | null;
}

export interface Estado {
  equipo: EquipoCfg | null; // equipo que muestra el lienzo (null = vista general)
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
  equipo: null,
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

export function valorNum(valores: Record<string, Valor>, v: string | undefined): number | null {
  if (!v) return null;
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
  (diag.hallazgos_secundarios ?? []).forEach((h) => add(h.aristas));
  return { aristas, nodos, fuente: 'diagnostico' };
}

/** Severidad del diagnostico para el color (ISA-101: color solo para lo anormal). Cubre todos los equipos. */
export function severidad(d?: string | null): 'normal' | 'aviso' | 'alarma' | 'info' {
  switch (d) {
    case 'REGULANDO':
    case 'LLENANDO':
    case 'NIVEL_ESTABLE':
    case 'EN_SETPOINT':
    case 'SUBIENDO_A_SETPOINT':
    case 'MANUAL_EN_MARCHA':
      return 'normal';
    case 'SATURADO_FUERA_DE_CAPACIDAD':
    case 'SIN_DATOS':
    case 'TANQUE1_NIVEL_BAJO':
    case 'ACTUADOR_NO_RESPONDE':
    case 'ERROR':
      return 'alarma';
    case 'SISTEMA_DETENIDO':
    case 'REMOTO_SIN_SETPOINT':
    case 'SOBRE_SETPOINT':
    case 'FUERA_DE_SETPOINT':
    case 'BOMBA_DETENIDA':
    case 'DESVIACION_SIN_SATURAR':
    case 'SATURADO_EN_MINIMO':
    case 'VACIANDO_CON_BOMBA':
    case 'REMOTO_SIN_SUPERVISOR':
    case 'SELECTOR_EN_0':
      return 'aviso';
    default:
      return 'info';
  }
}

/** Nombre legible de cada diagnostico (todos los equipos). */
export const NOMBRE_DIAG: Record<string, string> = {
  REGULANDO: 'Regulando',
  SATURADO_FUERA_DE_CAPACIDAD: 'Saturado: fuera de capacidad',
  SATURADO_EN_MINIMO: 'Saturado en el mínimo',
  BOMBA_DETENIDA: 'Bomba detenida',
  TRANSITORIO: 'Transitorio',
  CONTROL_MANUAL_LOCAL: 'Control manual (LOCAL)',
  PID_SIN_HABILITAR: 'PID sin habilitar',
  DESVIACION_SIN_SATURAR: 'Desviación sin saturar',
  SIN_DATOS: 'Sin datos en vivo',
  SELECTOR_EN_0: 'Selector en 0',
  REMOTO_SIN_SUPERVISOR: 'REMOTO sin HMI/SCADA',
  TANQUE1_NIVEL_BAJO: 'Tanque T1 en nivel bajo',
  APERTURA_INICIAL_VALVULA: 'Abriendo válvula (inicio)',
  LLENANDO: 'Llenando T2',
  NIVEL_ESTABLE: 'Nivel estable',
  VACIANDO_CON_BOMBA: 'Vaciando con bomba en marcha',
  SISTEMA_DETENIDO: 'Sistema detenido',
  MANUAL_EN_MARCHA: 'Marcha manual (LOCAL)',
  REMOTO_SIN_SETPOINT: 'REMOTO sin setpoint',
  ACTUADOR_NO_RESPONDE: 'Actuador no responde (lazo abierto)',
  SUBIENDO_A_SETPOINT: 'Subiendo al setpoint',
  EN_SETPOINT: 'En setpoint',
  SOBRE_SETPOINT: 'Sobre el setpoint',
  FUERA_DE_SETPOINT: 'Fuera del setpoint',
  ERROR: 'Error del diagnóstico',
};
