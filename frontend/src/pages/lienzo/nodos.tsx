import type { ReactNode } from 'react';
import type { Equipment, LevelDetail, NivelSenales } from '../../types';
import {
  IconAlert,
  IconFlow,
  IconGauge,
  IconLayers,
  IconLock,
  IconPanel,
  IconPlc,
  IconPump,
  IconSettings,
  IconSignal,
  IconTank,
  IconValve,
} from '../../components/common/Icons';
import type { Lectura, LienzoEdge, MetaNodo, Sev } from '../../lienzo/tipos';
import type { Diagnostico } from '../../components/lienzo/panels/DiagnosticoPanel';
import { construirDiagnostico } from '../../utils/diagnostico';
import { clamp, formatAge, num, timeOnly } from '../../utils/format';
import { DX, DY, GRAFOS, type GrafoNodo } from './grafoTesis';

export interface CtxLienzo {
  equipoId: string;
  eq: Equipment;
  valor: number;
  tsActual: string;
  historico: boolean;
  fresco: boolean;
  online: boolean;
  edad: string;
  age: number | null;
  momento: number | null;
  detalle?: LevelDetail | null;
  enlace?: string;
  /** Señales REALES del nivel (MQTT/UNS, conector edge ML1100). */
  senal?: NivelSenales | null;
}

/** Tamaño de los nodos del grafo (ANCHO_EQ de la tesis). */
const W_NODO = 236;

/** Relaciones que en la tesis se dibujan como flujo de proceso (línea sólida). */
const FLUJO = new Set(['alimenta', 'impulsa', 'descarga_en']);

const TIPO_TXT: Record<string, string> = {
  equipo: 'Equipo',
  sensor: 'Sensor',
  actuador: 'Actuador',
  control: 'Control',
  mando: 'Mando',
  proteccion: 'Protección',
  proceso: 'Proceso',
};

const TIPO_ICO: Record<string, ReactNode> = {
  equipo: <IconLayers />,
  sensor: <IconSignal />,
  actuador: <IconValve />,
  control: <IconSettings />,
  mando: <IconPanel />,
  proteccion: <IconLock />,
  proceso: <IconFlow />,
};

const SENSOR_PRINCIPAL: Record<string, string> = {
  'caudal-mcc09': 'caudalimetro',
  'nivel-mcn09': 'sensor_ultrasonico',
  'presion-mcp09': 'transmisor',
  'temp-mct09': 'sensor_principal',
};

const SIN_DATO: { texto: string; sev: Sev } = { texto: 'SIN DATO', sev: 'inactivo' };

/* ------------------------------------------------------ nodos (estáticos) */
/** Metadatos del grafo: no cambian con la telemetría (igual que en la tesis). */
export function metasDe(equipoId: string): MetaNodo[] {
  const grafo = GRAFOS[equipoId];
  if (!grafo) return [];

  return Object.entries(grafo.nodos).map(([id, meta]) => {
    const pos = grafo.layout[id] ?? [0, 0];
    return {
      id,
      x: (pos[0] ?? 0) + DX,
      y: (pos[1] ?? 0) + DY,
      w: W_NODO,
      tipo: TIPO_TXT[meta.tipo] ?? meta.tipo,
      nombre: meta.nombre,
      icono: TIPO_ICO[meta.tipo] ?? <IconTank />,
    };
  });
}

/** Lectura viva de cada nodo: se recalcula con la telemetría y llega por contexto. */
export function lecturasDe(ctx: CtxLienzo): Record<string, Lectura> {
  const grafo = GRAFOS[ctx.equipoId];
  if (!grafo) return {};
  const caido = enlaceCaido(ctx);
  const ultima = ultimaSenal(ctx);
  const salida: Record<string, Lectura> = {};
  for (const [id, meta] of Object.entries(grafo.nodos)) {
    const l = leer(id, meta, ctx);
    salida[id] = caido ? congelar(id, l, ultima) : l;
  }
  return salida;
}

/** Nodo del controlador físico de cada módulo (el único que se pinta en rojo si cae el enlace). */
const NODOS_PLC = new Set(['plc', 'pac']);

/**
 * ¿Se perdió el enlace con el PLC? (fuera de la red, conector apagado, PLC sin respuesta).
 * Nivel y caudal lo saben por sus señales MQTT; temperatura y presión por el estado del equipo.
 */
export function enlaceCaido(ctx: CtxLienzo): boolean {
  if (ctx.historico) return false;
  if (ctx.equipoId === 'nivel-mcn09' || ctx.equipoId === 'caudal-mcc09') return !ctx.senal || ctx.senal.plc !== 'CONECTADO';
  return !ctx.online;
}

/** Hora de la última señal recibida del PLC ('—' si nunca llegó). */
export function ultimaSenal(ctx: CtxLienzo): string {
  const ts = ctx.senal?.ultimo ?? ctx.eq.timestamp;
  const t = ts ? Date.parse(ts) : NaN;
  return Number.isFinite(t) && t > 86400000 ? timeOnly(ts as string) : '—';
}

/** Rojo solo en el PLC; el resto queda en gris con sus últimos valores (congelados). */
function congelar(id: string, l: Lectura, ultima: string): Lectura {
  if (NODOS_PLC.has(id)) {
    return {
      ...l,
      estado: { texto: 'PLC DESCONECTADO', sev: 'alarma' },
      filas: [...l.filas.filter((f) => f.k !== 'Última señal'), { k: 'Última señal', v: ultima }],
    };
  }
  return {
    ...l,
    congelado: true,
    estado: { texto: 'SIN SEÑAL', sev: 'inactivo' },
    barra: l.barra ? { ...l.barra, sev: 'inactivo' } : undefined,
  };
}

/* ---------------------------------------------------------------- aristas */
export function aristasDe(equipoId: string): LienzoEdge[] {
  const grafo = GRAFOS[equipoId];
  if (!grafo) return [];
  return grafo.relaciones.map((r) => ({
    de: r.de,
    a: r.a,
    rel: r.rel,
    flujo: FLUJO.has(r.rel),
  }));
}

/* ------------------------------------------------- nivel: datos REALES (MQTT) */
const DESCONECTADO: { texto: string; sev: Sev } = { texto: 'PLC DESCONECTADO', sev: 'alarma' };
const SIN_DATO_EST: { texto: string; sev: Sev } = { texto: 'SIN DATO', sev: 'inactivo' };

/** Valor numérico de una señal publicada por el conector edge (null = sin dato). */
function sNum(s: NivelSenales | null | undefined, k: string): number | null {
  const v = s?.valores?.[k]?.valor;
  if (typeof v === 'number') return v;
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return Number(v);
  return null;
}

/** Bit/booleano de una señal (null = sin dato). */
function sBool(s: NivelSenales | null | undefined, k: string): boolean | null {
  const v = s?.valores?.[k]?.valor;
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return Math.abs(v) > 0.5;
  if (typeof v === 'string') {
    const t = v.trim().toLowerCase();
    if (t === 'true' || t === 'on' || t === '1') return true;
    if (t === 'false' || t === 'off' || t === '0') return false;
    if (!Number.isNaN(Number(t))) return Math.abs(Number(t)) > 0.5;
  }
  return null;
}

const sFmt = (v: number | null, d = 1) => (v === null ? 'Sin datos' : num(v, d));
const sBit = (v: boolean | null) => (v === null ? 'Sin datos' : v ? 'ON' : 'OFF');

/** Color del selector: REMOTO verde · LOCAL azul · EN 0 ámbar (nadie tiene el mando). */
export function sevModo(modo: string): Sev {
  const m = modo.toUpperCase();
  return m === 'REMOTO' ? 'activo' : m === 'LOCAL' ? 'info' : 'aviso';
}

/** Modo real del selector LOCAL/REMOTO (null = sin datos). */
export function senalModo(s: NivelSenales | null | undefined): string | null {
  const remoto = sBool(s, 'estado/selector_remoto');
  const local = sBool(s, 'estado/selector_local');
  if (remoto === null && local === null) return null;
  if (remoto === true) return 'REMOTO';
  if (local === true) return 'LOCAL';
  return 'EN 0';
}

/**
 * Lectura del módulo de nivel a partir EXCLUSIVAMENTE de las señales reales
 * (MQTT/UNS). Sin datos → "SIN DATO"; sin conexión al PLC → "PLC DESCONECTADO".
 */
function leerNivel(id: string, ctx: CtxLienzo): Lectura {
  const s = ctx.senal;
  const desconectado = !s || s.plc !== 'CONECTADO';
  const num = (k: string) => sNum(s, k);
  const bit = (k: string) => sBool(s, k);
  const edad = s?.ultimo ? timeOnly(s.ultimo) : 'Sin datos';

  /* Modo histórico: solo existe el historial de nivel/cm */
  if (ctx.historico) {
    if (id === 'sensor_ultrasonico' || id === 'tanque_t2') {
      return {
        estado: { texto: 'MOMENTO HISTÓRICO', sev: 'info' },
        principal: { valor: num2(ctx.valor), unidad: 'cm' },
        filas: [{ k: 'Muestra', v: timeOnly(ctx.tsActual) }],
      };
    }
    return { estado: { texto: 'MOMENTO HISTÓRICO', sev: 'info' }, filas: [{ k: 'Dispositivo', v: 'Sin histórico' }] };
  }

  const off = (filas: Lectura['filas']): Lectura => ({ estado: DESCONECTADO, filas });

  switch (id) {
    case 'sensor_ultrasonico': {
      const cm = num('nivel/cm');
      return {
        estado: desconectado ? DESCONECTADO : cm === null ? SIN_DATO_EST : { texto: 'MIDIENDO', sev: 'activo' },
        principal: cm === null ? undefined : { valor: num2(cm), unidad: 'cm' },
        filas: [
          { k: 'N7:4 (crudo)', v: sFmt(num('nivel/raw'), 0), u: 'cuentas' },
          { k: 'Altura tanque', v: s?.alturaCm != null ? num2(s.alturaCm, 0) : 'Sin datos', u: s?.alturaCm != null ? 'cm' : undefined },
        ],
      };
    }
    case 'pid': {
      const cv = num('pid/cv_raw');
      return {
        estado: desconectado
          ? DESCONECTADO
          : cv === null
            ? SIN_DATO_EST
            : { texto: 'SALIDA PUBLICADA', sev: 'activo' },
        filas: [
          { k: 'SP (N7:5)', v: sFmt(num('pid/setpoint_a_raw'), 0), u: 'cuentas' },
          { k: 'PV (N7:4)', v: sFmt(num('nivel/raw'), 0), u: 'cuentas' },
          { k: 'Salida (N7:14)', v: sFmt(cv, 0), u: 'cuentas' },
          { k: 'Kc · Ti', v: `${sFmt(num('pid/kc_a'), 2)} · ${sFmt(num('pid/ti_a'), 2)}` },
        ],
      };
    }
    case 'plc':
      return {
        estado: desconectado ? DESCONECTADO : { texto: 'CONECTADO', sev: 'activo' },
        filas: [
          { k: 'Enlace', v: 'EtherNet/IP (PCCC)' },
          { k: 'Conector edge', v: s?.edge ?? 'Sin datos' },
          { k: 'Última señal', v: edad },
        ],
      };
    case 'selector': {
      const modo = senalModo(s);
      return {
        estado: desconectado
          ? DESCONECTADO
          : modo === null
            ? SIN_DATO_EST
            : { texto: modo, sev: sevModo(modo) },
        filas: [{ k: 'Posición', v: modo ?? 'Sin datos' }],
      };
    }
    case 'bomba': {
      const marcha = bit('estado/bomba_marcha');
      return {
        estado: desconectado
          ? DESCONECTADO
          : marcha === null
            ? SIN_DATO_EST
            : marcha
              ? { texto: 'EN MARCHA', sev: 'activo' }
              : { texto: 'DETENIDA', sev: 'inactivo' },
        filas: [
          { k: 'Frecuencia', v: sFmt(num('bomba/frecuencia_estimada_hz')), u: 'Hz' },
          { k: 'Salida PLC (O:1.0)', v: sFmt(num('bomba/salida_plc_raw'), 0), u: 'cuentas' },
        ],
      };
    }
    case 'variador': {
      const hz = num('bomba/frecuencia_estimada_hz');
      return {
        estado: desconectado ? DESCONECTADO : hz === null ? SIN_DATO_EST : { texto: 'RECIBIENDO MANDO', sev: 'activo' },
        filas: [
          { k: 'Frecuencia', v: sFmt(hz), u: 'Hz' },
          { k: 'Potenciómetro (I:1.5)', v: sFmt(num('bomba/potenciometro_raw'), 0), u: 'cuentas' },
          { k: 'Salida PLC', v: sFmt(num('bomba/salida_plc_raw'), 0), u: 'cuentas' },
        ],
      };
    }
    case 'valvula': {
      const abr = bit('valvula/abriendo');
      const cerr = bit('valvula/cerrando');
      return {
        estado: desconectado
          ? DESCONECTADO
          : abr === null && cerr === null
            ? SIN_DATO_EST
            : abr === true
              ? { texto: 'ABRIENDO', sev: 'aviso' }
              : cerr === true
                ? { texto: 'CERRANDO', sev: 'aviso' }
                : { texto: 'EN REPOSO', sev: 'normal' },
        filas: [
          { k: 'T4:0.ACC', v: sFmt(num('valvula/t_apertura')), u: 's' },
          { k: 'T4:1.ACC', v: sFmt(num('valvula/t_cierre')), u: 's' },
        ],
      };
    }
    case 'tanque_t2': {
      const pct = num('nivel/pct');
      const cm = num('nivel/cm');
      const saturado = bit('nivel/fuera_rango_sensor');
      return {
        estado: desconectado
          ? DESCONECTADO
          : pct === null && saturado === null
            ? SIN_DATO_EST
            : saturado === true
              ? { texto: 'SENSOR SATURADO', sev: 'alarma' }
              : { texto: 'NIVEL MEDIDO', sev: 'normal' },
        principal: cm === null ? undefined : { valor: num2(cm), unidad: 'cm' },
        barra:
          pct === null
            ? undefined
            : { pct: clamp(pct), sev: saturado === true ? 'alarma' : 'normal', etiqueta: `${num2(pct)} % lleno` },
        filas: [
          { k: 'Capacidad', v: s?.alturaCm != null ? num2(s.alturaCm, 0) : 'Sin datos', u: s?.alturaCm != null ? 'cm' : undefined },
          { k: 'Antigüedad', v: edad },
        ],
      };
    }
    case 'tanque_t1': {
      const conAgua = bit('estado/tanque1_con_agua');
      return {
        estado: desconectado
          ? DESCONECTADO
          : conAgua === null
            ? SIN_DATO_EST
            : conAgua
              ? { texto: 'CON AGUA', sev: 'activo' }
              : { texto: 'NIVEL BAJO', sev: 'alarma' },
        filas: [{ k: 'Piloto bajo (O:0/1)', v: sBit(bit('estado/alarma_nivel_bajo_tanque1')) }],
      };
    }
    case 'interruptor_nivel_t1': {
      const conAgua = bit('estado/tanque1_con_agua');
      return {
        estado: desconectado
          ? DESCONECTADO
          : conAgua === null
            ? SIN_DATO_EST
            : conAgua
              ? { texto: 'SEÑAL EN 1', sev: 'normal' }
              : { texto: 'NIVEL BAJO', sev: 'alarma' },
        filas: [
          { k: 'Entrada I:0/2', v: sBit(conAgua) },
          { k: 'Piloto O:0/1', v: sBit(bit('estado/alarma_nivel_bajo_tanque1')) },
        ],
      };
    }
    case 'potenciometro': {
      const pot = num('bomba/potenciometro_raw');
      return {
        estado: desconectado ? DESCONECTADO : pot === null ? SIN_DATO_EST : { texto: 'LECTURA REAL', sev: 'activo' },
        filas: [
          { k: 'Valor (I:1.5)', v: sFmt(pot, 0), u: 'cuentas' },
          { k: 'Frecuencia (est.)', v: sFmt(num('bomba/frecuencia_estimada_hz')), u: 'Hz' },
        ],
      };
    }
    case 'pulsadores': {
      const pulso = bit('estado/pulsador_arranque');
      return {
        estado: desconectado
          ? DESCONECTADO
          : pulso === true
            ? { texto: 'ARRANQUE PULSADO', sev: 'aviso' }
            : SIN_DATO_EST,
        filas: [{ k: 'Entrada I:0/4', v: sBit(pulso) }],
      };
    }
    case 'hmi':
    case 'pc_scada':
      /* sin fuente de datos publicada para estos nodos (la tesis también los marca sin comunicación) */
      return { estado: SIN_DATO_EST, filas: [{ k: 'Comunicación', v: 'Sin datos' }] };
    default:
      return off(metaVariablesVacias(id, s));
  }
}

/** Filas genéricas: variables del grafo sin dato publicado. */
function metaVariablesVacias(id: string, s: NivelSenales | null | undefined): Lectura['filas'] {
  const grafoNodo = Object.values(GRAFOS).flatMap((g) => Object.entries(g.nodos)).find(([k]) => k === id)?.[1];
  const vars = grafoNodo?.variables ?? [];
  return vars.slice(0, 3).map((v) => ({ k: v.split('/').pop() ?? v, v: 'Sin datos' }));
}

const num2 = (v: number, d = 1) => num(v, d);

/* -------------------------------------------------------------- lecturas */
function leer(id: string, meta: GrafoNodo, ctx: CtxLienzo): Lectura {
  /* El módulo de nivel usa exclusivamente datos reales (MQTT/UNS) */
  if (ctx.equipoId === 'nivel-mcn09') return leerNivel(id, ctx);

  /* Caudal usa las señales MQTT reales que ya alimentan el lienzo técnico. */
  if (ctx.equipoId === 'caudal-mcc09' && !ctx.historico) {
    const s = ctx.senal;
    const n = (k: string) => sNum(s, k);
    const b = (k: string) => sBool(s, k);
    const desconectado = !s || s.plc !== 'CONECTADO';
    const activo: { texto: string; sev: Sev } = desconectado ? DESCONECTADO : { texto: 'LECTURA REAL', sev: 'activo' };
    if (id === 'caudalimetro' || id === 'linea') return {
      estado: activo,
      principal: n('caudal/pv_pid') == null ? undefined : { valor: sFmt(n('caudal/pv_pid')), unidad: 'L/min' },
      filas: [{ k: 'Setpoint', v: sFmt(n('caudal/setpoint_pid')), u: 'L/min' }],
    };
    if (id === 'plc') return { estado: desconectado ? DESCONECTADO : { texto: 'CONECTADO', sev: 'activo' }, filas: [{ k: 'Enlace', v: 'S7-200 · CP243-1' }] };
    if (id === 'selector') { const m = senalModo(s); return { estado: desconectado ? DESCONECTADO : m === null ? SIN_DATO_EST : { texto: m, sev: sevModo(m) }, filas: [] }; }
    if (id === 'bomba') return { estado: desconectado ? DESCONECTADO : b('estado/sistema_funcionando') ? { texto: 'EN MARCHA', sev: 'activo' } : { texto: 'DETENIDA', sev: 'inactivo' }, filas: [{ k: 'Variador', v: sFmt(n('actuadores/variador_pct')), u: '%' }] };
    if (id === 'variador') return { estado: activo, filas: [{ k: 'Orden RUN (Q1.1)', v: sBit(b('io/q1_1')) }], barra: n('actuadores/variador_pct') == null ? undefined : { pct: clamp(n('actuadores/variador_pct')!), sev: 'normal', etiqueta: `${sFmt(n('actuadores/variador_pct'))} %` } };
    if (id === 'valvula') return { estado: activo, barra: n('actuadores/valvula_pct') == null ? undefined : { pct: clamp(n('actuadores/valvula_pct')!), sev: 'normal', etiqueta: `${sFmt(n('actuadores/valvula_pct'))} %` }, filas: [] };
    if (id === 'pid') return { estado: activo, filas: [
      { k: 'SP', v: sFmt(n('caudal/setpoint_pid')), u: 'L/min' }, { k: 'PV', v: sFmt(n('caudal/pv_pid')), u: 'L/min' },
      { k: 'Salida', v: sFmt(n('pid/salida')), u: '%' }, { k: 'Kc · Ti', v: `${sFmt(n('pid/kc'), 2)} · ${sFmt(n('pid/ti'), 2)}` },
    ] };
    /* Mandos de consigna: M0.3 = 1 manda la HMI (VD408); M0.3 = 0 manda la PC (VD400) */
    const hmiManda = b('estado/modo_hmi_pc');
    if (id === 'pc_scada') return {
      estado: desconectado ? DESCONECTADO : hmiManda === null ? SIN_DATO_EST : hmiManda ? { texto: 'EN ESPERA', sev: 'inactivo' } : { texto: 'EN MANDO', sev: 'activo' },
      filas: [{ k: 'Setpoint remoto', v: sFmt(n('caudal/setpoint')), u: 'L/min' }, { k: 'Arranque remoto', v: sBit(b('estado/start_remoto')) }],
    };
    if (id === 'hmi') return {
      estado: desconectado ? DESCONECTADO : hmiManda === null ? SIN_DATO_EST : hmiManda ? { texto: 'EN MANDO', sev: 'activo' } : { texto: 'EN ESPERA', sev: 'inactivo' },
      filas: [{ k: 'Setpoint HMI', v: sFmt(n('caudal/setpoint_hmi')), u: 'L/min' }],
    };
    /* Switches de nivel del tanque: Q0.0 nivel alto · Q0.1 nivel bajo (= NOT I0.2) */
    const bajo = b('estado/nivel_bajo'), alto = b('estado/nivel_alto');
    const nivelEst = desconectado ? DESCONECTADO : bajo === null && alto === null ? SIN_DATO_EST
      : bajo ? { texto: 'NIVEL BAJO', sev: 'alarma' as Sev } : alto ? { texto: 'NIVEL ALTO', sev: 'alarma' as Sev } : { texto: 'NIVEL OK', sev: 'activo' as Sev };
    if (id === 'tanque') return { estado: nivelEst, filas: [{ k: 'Nivel bajo', v: sBit(bajo) }, { k: 'Nivel alto', v: sBit(alto) }] };
    if (id === 'sensor_nivel') return {
      estado: desconectado ? DESCONECTADO : bajo === null ? SIN_DATO_EST : bajo ? { texto: 'SIN AGUA', sev: 'alarma' } : { texto: 'CON AGUA', sev: 'activo' },
      filas: [{ k: 'Nivel bajo (Q0.1)', v: sBit(bajo) }],
    };
    if (id === 'sensor_nivel_alto') return {
      estado: desconectado ? DESCONECTADO : alto === null ? SIN_DATO_EST : alto ? { texto: 'NIVEL ALTO', sev: 'alarma' } : { texto: 'NORMAL', sev: 'activo' },
      filas: [{ k: 'Nivel alto (Q0.0)', v: sBit(alto) }],
    };
    /* Guardamotor: sin señal al PLC -> se INFIERE el disparo (marcha + caudal 0 + PID saturado) */
    if (id === 'proteccion_motor') {
      const marcha = b('estado/sistema_funcionando'), q = n('caudal/pv_pid'), salida = n('pid/salida');
      const posible = marcha === true && q != null && q < 0.5 && salida != null && salida >= 95;
      return {
        estado: desconectado ? DESCONECTADO : posible ? { texto: 'POSIBLE DISPARO', sev: 'alarma' } : { texto: 'SIN SEÑAL AL PLC', sev: 'inactivo' },
        filas: [{ k: 'Disparo', v: posible ? 'inferido: marcha sin caudal' : 'se infiere del caudal' }, { k: 'Riesgo', v: 'LOCAL + potenc. al máx.' }],
      };
    }
    /* Variador: Q1.1 = orden RUN */
    /* El potenciómetro solo existe en modo LOCAL (en REMOTO MW2 es basura y no se publica) */
    if (id === 'potenciometro') {
      /* el valor queda RETENIDO en el broker desde la última vez en LOCAL: solo vale si el selector está en LOCAL */
      const pot = senalModo(s) === 'LOCAL' ? n('actuadores/potenciometro') : null;
      return pot == null
        ? { estado: desconectado ? DESCONECTADO : { texto: 'SOLO EN LOCAL', sev: 'inactivo' }, filas: [{ k: 'Valor', v: 'activo en LOCAL' }] }
        : { estado: activo, filas: [{ k: 'Valor', v: sFmt(pot, 0), u: 'cuentas' }] };
    }
  }

  const { eq, valor, historico, fresco, online, detalle, edad, tsActual } = ctx;

  /* --- niveles de tanque (switches) de presión y temperatura: PLC real o planta simulada --- */
  if (!historico) {
    const t = leerTanques(id, ctx);
    if (t) return t;
  }
  const unit = eq.unit;
  const alto = valor > eq.setpoint * 1.12;
  const bajo = valor < eq.setpoint * 0.88;
  const principal = SENSOR_PRINCIPAL[ctx.equipoId];

  /* --- sensor principal con dato real --- */
  if (id === principal) {
    return {
      estado: historico
        ? { texto: 'MOMENTO HISTÓRICO', sev: 'info' }
        : fresco
          ? { texto: 'MIDIENDO', sev: 'activo' }
          : SIN_DATO,
      principal: { valor: num(valor, unit === 'psi' ? 2 : 1), unidad: unit },
      filas:
        ctx.equipoId === 'caudal-mcc09'
          ? [
              { k: 'Crudo AIW0', v: 'Sin datos', u: 'cuentas' },
              { k: 'Δ vs PV del PID', v: 'Sin datos', u: unit },
            ]
          : [
              { k: 'Consigna', v: num(eq.setpoint, 2), u: unit },
              { k: 'Desviación', v: num(valor - eq.setpoint, 2), u: unit },
            ],
    };
  }

  /* --- lazo PID --- */
  if (id === 'pid') {
    /* salida y sintonía reales del PLC (temperatura: pid/salida_pct · presión: pid/cv) */
    const sp = ctx.senal;
    const salida = historico ? null : (sNum(sp, 'pid/salida_pct') ?? sNum(sp, 'pid/cv'));
    const kp = sNum(sp, 'pid/kp'), ti = sNum(sp, 'pid/ti'), td = sNum(sp, 'pid/td');
    /* lazo en marcha según el PLC (null = el módulo no publica esa señal) */
    const marcha = historico ? null : sBool(sp, 'estado/sistema_funcionando');
    const f = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(2));
    const sintonia = historico || kp == null || ti == null ? 'Sin datos' : `${f(kp)} · ${f(ti)}${td == null ? '' : ` · ${f(td)}`}`;
    return {
      /* solo se evalúa la banda si el lazo está EN MARCHA y tiene consigna */
      estado: historico
        ? { texto: 'HISTÓRICO', sev: 'inactivo' }
        : !fresco
          ? SIN_DATO
          : marcha === false
            ? { texto: 'DETENIDO', sev: 'inactivo' }
            : eq.setpoint <= 0
              ? { texto: 'SIN CONSIGNA', sev: 'inactivo' }
              : alto || bajo
                ? { texto: 'FUERA DE BANDA', sev: 'alarma' }
                : { texto: 'REGULANDO', sev: 'activo' },
      filas: [
        { k: 'SP', v: num(eq.setpoint, 1), u: unit },
        { k: 'PV', v: num(valor, 1), u: unit },
        { k: 'Salida', v: salida == null ? 'Sin datos' : num(salida, 1), u: salida == null ? undefined : '%' },
        { k: td == null ? 'Kp · Ti' : 'Kp · Ti · Td', v: sintonia },
      ],
    };
  }

  /* --- controlador físico --- */
  if (id === 'plc') {
    return {
      estado: historico
        ? { texto: 'HISTÓRICO', sev: 'inactivo' }
        : online
          ? { texto: 'CONECTADO', sev: 'activo' }
          : { texto: 'SIN CONEXIÓN', sev: 'alarma' },
      filas: [{ k: 'Enlace', v: ctx.enlace ?? 'Sin datos' }],
    };
  }

  /* --- proceso (línea / tanque de trabajo) --- */
  if (id === 'linea' || (id === 'tanque_t2' && ctx.equipoId === 'nivel-mcn09')) {
    const pct = clamp((valor / (detalle?.tankHeight ?? 20)) * 100);
    const esTanque = id === 'tanque_t2';
    return {
      estado: historico
        ? { texto: 'MOMENTO HISTÓRICO', sev: 'info' }
        : alto || bajo
          ? { texto: esTanque ? (alto ? 'NIVEL ALTO' : 'NIVEL BAJO') : 'FUERA DE BANDA', sev: 'alarma' }
          : fresco
            ? { texto: 'OPERANDO', sev: 'normal' }
            : { texto: 'SIN COMUNICACIÓN', sev: 'inactivo' },
      principal: esTanque ? { valor: num(valor, 2), unidad: unit } : { valor: num(valor, 1), unidad: unit },
      barra: {
        pct: esTanque ? pct : clamp((valor / (eq.setpoint * 1.5)) * 100),
        sev: alto || bajo ? 'alarma' : 'normal',
        etiqueta: esTanque ? `${num(pct, 1)} % lleno` : `${num(clamp((valor / (eq.setpoint * 1.5)) * 100), 0)} % de la escala`,
      },
      filas: [
        { k: 'Setpoint', v: num(eq.setpoint, 1), u: unit },
        { k: historico ? 'Momento' : 'Antigüedad', v: edad },
      ],
    };
  }

  /* --- bomba --- */
  if (id === 'bomba') {
    const marcha = ctx.equipoId === 'nivel-mcn09' && detalle ? detalle.pumpOn : null;
    return {
      estado: historico
        ? { texto: 'SIN HISTÓRICO', sev: 'inactivo' }
        : marcha === null
          ? SIN_DATO
          : marcha
            ? { texto: 'EN MARCHA', sev: 'activo' }
            : { texto: 'DETENIDA', sev: 'inactivo' },
      filas: [
        { k: 'Velocidad (consigna)', v: marcha === null ? 'Sin datos' : num(detalle?.vfdPercent ?? 0, 0), u: '%' },
      ],
    };
  }

  /* --- variador --- */
  if (id === 'variador') {
    const disponible = ctx.equipoId === 'nivel-mcn09' && detalle;
    return {
      estado: historico ? { texto: 'SIN HISTÓRICO', sev: 'inactivo' } : disponible ? undefined : SIN_DATO,
      barra: disponible
        ? { pct: clamp(detalle?.vfdPercent ?? 0), sev: 'normal', etiqueta: `${num(detalle?.vfdPercent ?? 0, 1)} %` }
        : undefined,
      filas: [
        { k: 'Mando', v: disponible ? 'Salida PID' : 'Sin datos' },
        { k: 'Frecuencia', v: disponible ? num(detalle?.vfdHz ?? 0, 1) : 'Sin datos', u: 'Hz' },
      ],
    };
  }

  /* --- válvula --- */
  if (id === 'valvula') {
    const disponible = ctx.equipoId === 'nivel-mcn09' && detalle;
    return {
      estado: historico ? { texto: 'SIN HISTÓRICO', sev: 'inactivo' } : disponible ? { texto: 'BAJO SUPERVISIÓN', sev: 'normal' } : SIN_DATO,
      barra: disponible
        ? { pct: clamp(detalle?.valveOpen ?? 0), sev: 'normal', etiqueta: `${num(detalle?.valveOpen ?? 0, 1)} % abierta` }
        : undefined,
      filas: [{ k: 'Apertura', v: disponible ? num(detalle?.valveOpen ?? 0, 1) : 'Sin datos', u: '%' }],
    };
  }

  /* --- selector LOCAL/REMOTO --- */
  if (id === 'selector') {
    const modo = ctx.equipoId === 'nivel-mcn09' && detalle ? detalle.mode : null;
    return {
      estado: historico
        ? { texto: 'HISTÓRICO', sev: 'inactivo' }
        : modo
          ? { texto: modo, sev: sevModo(modo) }
          : SIN_DATO,
      filas: [{ k: 'Posición', v: modo ?? 'Sin datos' }],
    };
  }

  /* --- mandos de tablero / supervisión sin señal --- */
  if (id === 'potenciometro' || id === 'potenciometro_variador') {
    return { estado: SIN_DATO, filas: [{ k: 'Valor', v: 'Sin datos', u: 'cuentas' }] };
  }
  if (id === 'pc_scada') {
    return { estado: { texto: 'EN ESPERA', sev: 'inactivo' }, filas: [{ k: 'Setpoint remoto', v: 'Sin datos', u: unit }] };
  }
  if (id === 'hmi') {
    return { estado: { texto: 'EN ESPERA', sev: 'inactivo' }, filas: [{ k: 'Setpoint HMI', v: 'Sin datos', u: unit }] };
  }
  if (id === 'pulsadores') {
    return { estado: SIN_DATO, filas: [{ k: 'Arranque manual', v: 'Sin datos' }] };
  }
  if (id === 'proteccion_motor') {
    return { estado: { texto: 'SIN SEÑAL AL PLC', sev: 'inactivo' }, filas: [{ k: 'Disparo', v: 'Sin datos' }] };
  }

  /* --- genérico: lista las variables del nodo como en la tesis (fallback) --- */
  return {
    estado: SIN_DATO,
    filas: meta.variables.slice(0, 3).map((v) => ({ k: v.split('/').pop() ?? v, v: 'Sin datos' })),
  };
}

/* ------------------------------------- niveles de tanque (presión / temperatura) */
interface Tanque { pct: number | null; alto: boolean | null; bajo: boolean | null }

/** Niveles de cada tanque: en planta simulada salen de las llaves (sim/*), en real de los switches del PLC. */
function tanquesDe(ctx: CtxLienzo): Record<'t1' | 't2', Tanque | null> | null {
  const s = ctx.senal;
  const n = (k: string) => sNum(s, k);
  const b = (k: string) => sBool(s, k);
  const no = (v: boolean | null) => (v === null ? null : !v);
  const sim = s?.valores?.['sim/planta'] != null || s?.valores?.['sim/t1_pct'] != null;
  const simT = (k: 't1' | 't2'): Tanque => ({ pct: n(`sim/${k}_pct`), alto: b(`sim/${k}_alto`), bajo: b(`sim/${k}_bajo`) });
  if (ctx.equipoId === 'presion-mcp09')
    return { t1: sim ? simT('t1') : { pct: null, alto: b('estado/alarma_nivel_alto'), bajo: b('estado/alarma_nivel_bajo') }, t2: null };
  if (ctx.equipoId === 'temp-mct09')
    return sim
      ? { t1: simT('t1'), t2: simT('t2') }
      : {
          t1: { pct: null, alto: b('nivel/enfriador_alto'), bajo: no(b('nivel/enfriador_bajo_ok')) },
          t2: { pct: null, alto: b('nivel/principal_alto'), bajo: no(b('nivel/principal_bajo_ok')) },
        };
  return null;
}

function estTanque(t: Tanque | null): { texto: string; sev: Sev } {
  if (!t || (t.alto === null && t.bajo === null)) return SIN_DATO;
  if (t.bajo) return { texto: 'NIVEL BAJO', sev: 'alarma' };
  if (t.alto) return { texto: 'NIVEL ALTO', sev: 'alarma' };
  return { texto: 'NIVEL OK', sev: 'activo' };
}

function barraTanque(t: Tanque | null): Lectura['barra'] {
  if (!t || t.pct == null) return undefined;
  return { pct: clamp(t.pct), sev: t.alto || t.bajo ? 'alarma' : 'normal', etiqueta: `${num(t.pct, 0)} % lleno` };
}

const filasTanque = (t: Tanque | null): Lectura['filas'] => [
  { k: 'Nivel bajo', v: sBit(t?.bajo ?? null) },
  { k: 'Nivel alto', v: sBit(t?.alto ?? null) },
];

/** Nodos de tanques y de sus interruptores de nivel (null = el nodo no es de niveles). */
function leerTanques(id: string, ctx: CtxLienzo): Lectura | null {
  const tq = tanquesDe(ctx);
  if (!tq) return null;
  const temp = (k: string) => {
    const v = sNum(ctx.senal, k);
    return v == null ? undefined : { valor: num(v, 1), unidad: '°C' };
  };
  if (ctx.equipoId === 'presion-mcp09') {
    if (id === 'tanque_t1') return { estado: estTanque(tq.t1), barra: barraTanque(tq.t1), filas: filasTanque(tq.t1) };
    if (id === 'interruptores_nivel_t1') return { estado: estTanque(tq.t1), filas: filasTanque(tq.t1) };
    return null;
  }
  /* temperatura: T1 = enfriamiento (arriba) · T2 = principal (abajo, con la resistencia) */
  if (id === 'sensor_enfriador') {
    const t = temp('temperatura/enfriador_c');
    return { estado: t ? { texto: 'MIDIENDO', sev: 'activo' } : SIN_DATO, principal: t, filas: [{ k: 'Crudo %MW1', v: sFmt(sNum(ctx.senal, 'temperatura/enfriador_raw'), 0), u: 'cuentas' }] };
  }
  if (id === 'tanque_enfriador')
    return { estado: estTanque(tq.t1), principal: temp('temperatura/enfriador_c'), barra: barraTanque(tq.t1), filas: filasTanque(tq.t1) };
  if (id === 'tanque_principal')
    return { estado: estTanque(tq.t2), principal: temp('temperatura/principal_c'), barra: barraTanque(tq.t2), filas: filasTanque(tq.t2) };
  if (id === 'interruptores_nivel') {
    const e1 = estTanque(tq.t1), e2 = estTanque(tq.t2);
    const mal = [e2.sev === 'alarma' ? `${e2.texto} T2` : null, e1.sev === 'alarma' ? `${e1.texto} T1` : null].filter(Boolean);
    const estado = mal.length ? { texto: mal.join(' · '), sev: 'alarma' as Sev } : e1 === SIN_DATO && e2 === SIN_DATO ? SIN_DATO : { texto: 'NIVELES OK', sev: 'activo' as Sev };
    const txt = (e: { texto: string }) => (e === SIN_DATO ? 'Sin datos' : e.texto.replace('NIVEL ', ''));
    return { estado, filas: [{ k: 'Principal (T2)', v: txt(e2) }, { k: 'Enfriamiento (T1)', v: txt(e1) }] };
  }
  return null;
}

/* ------------------------------------------------------------- diagnóstico */
export function diagnosticoDe(ctx: CtxLienzo): Diagnostico {
  const { eq, tsActual, historico, edad, age, momento, senal } = ctx;
  const esNivel = ctx.equipoId === 'nivel-mcn09';
  const esCaudal = ctx.equipoId === 'caudal-mcc09';
  const valor = esCaudal && !historico ? (sNum(senal, 'caudal/pv_pid') ?? ctx.valor) : ctx.valor;
  const setpoint = esCaudal && !historico
    ? (sNum(senal, 'caudal/setpoint_pid') ?? sNum(senal, 'caudal/setpoint') ?? eq.setpoint)
    : eq.setpoint;
  const tsVivo = esCaudal && !historico ? (senal?.ultimo ?? tsActual) : tsActual;
  const edadViva = esCaudal && !historico && senal?.ultimo
    ? formatAge(Math.max(0, (Date.now() - Date.parse(senal.ultimo)) / 1000))
    : age !== null ? formatAge(age) : edad;

  /* Nota del nivel: solo con señales reales del conector edge */
  let nota: string | undefined;
  if (esNivel && !historico && senal?.plc === 'CONECTADO') {
    const marcha = sBool(senal, 'estado/bomba_marcha');
    const modo = senalModo(senal);
    const hz = sNum(senal, 'bomba/frecuencia_estimada_hz');
    const partes = [
      marcha === null ? 'bomba sin dato' : `bomba ${marcha ? 'encendida' : 'detenida'}`,
      modo === null ? 'modo sin dato' : `modo ${modo}`,
      hz === null ? null : `${num(hz, 1)} Hz`,
    ].filter(Boolean);
    if (partes.length) nota = `${partes.join(', ')}.`;
  }

  return construirDiagnostico({
    equipo: eq.name,
    valor,
    setpoint,
    unit: eq.unit,
    tolerancia: esNivel ? 0.15 : 0.12,
    online: esNivel || esCaudal ? senal?.mqtt === true && senal?.plc === 'CONECTADO' : eq.status === 'ONLINE',
    historico,
    momentoTexto: `${historico ? 'Reproducción' : 'En vivo'} · ${timeOnly(tsVivo)}`,
    edad: historico ? timeOnly(momento ?? Date.now()) : edadViva,
    cadena: cadenaDe(ctx.equipoId),
    nota,
  });
}

export function cadenaDe(equipoId: string): Array<{ de: string; rel: string; a: string }> {
  const grafo = GRAFOS[equipoId];
  if (!grafo) return [];
  return grafo.relaciones
    .filter((r) => r.de === 'pid' || r.a === 'pid' || r.de === 'plc' || r.rel === 'impulsa' || r.rel === 'mide')
    .slice(0, 5)
    .map((r) => ({ de: r.de, rel: r.rel.replace(/_/g, ' '), a: r.a }));
}

/* ---------------------------------------------------------- paneles (canvas) */
export interface PanelLienzo {
  kind: 'diagnostico' | 'agente' | 'tendencia' | 'uns';
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Tamaños idénticos a PANELES de VistaEquipo.tsx de la tesis. */
const PANELES: [PanelLienzo['kind'], number, number][] = [
  ['diagnostico', 400, 470],
  ['agente', 400, 560],
  ['tendencia', 820, 330],
  ['uns', 400, 330],
];

/**
 * Posiciones de los 4 paneles DENTRO del lienzo: salen del layout del grafo
 * (`panel:*`, igual que la tesis) y aplican el mismo desplazamiento DX/DY
 * que usan los nodos del equipo.
 */
export function panelesDe(equipoId: string): PanelLienzo[] {
  const grafo = GRAFOS[equipoId];
  return PANELES.map(([kind, w, h]) => {
    const pos = grafo?.layout[`panel:${kind}`];
    return { kind, w, h, x: (pos?.[0] ?? 1300) + DX, y: (pos?.[1] ?? 0) + DY };
  });
}
