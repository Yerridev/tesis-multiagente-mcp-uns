import type { Diagnostico, Enlace, Valor } from '../types';
import { valorNum } from '../ctx';
import { fmtNum } from '../api';

export type Sev = 'normal' | 'activo' | 'aviso' | 'alarma' | 'inactivo';

export interface Lectura {
  estado?: { texto: string; sev: Sev };
  principal?: { valor: string; unidad: string };
  barra?: { pct: number; sev: Sev; etiqueta: string };
  filas: { k: string; v: string; u?: string }[];
}

type Fn = (id: string, variables: string[], V: Record<string, Valor>, enlace: Enlace | null, diag: Diagnostico | null) => Lectura;

const pct = (v: number | null) => (v === null ? null : Math.max(0, Math.min(100, v)));

/** Lectura generica: las primeras variables del nodo con su unidad (para nodos nuevos o equipos sin reglas). */
const generica: Fn = (_id, variables, V) => ({
  filas: variables.slice(0, 4).map((v) => ({ k: v.split('/').pop() ?? v, v: fmtNum(valorNum(V, v), 2), u: V[v]?.unidad ?? '' })),
});

const plcEstado = (enlace: Enlace | null, detalle: string): Lectura => ({
  estado: !enlace ? { texto: 'HISTÓRICO', sev: 'inactivo' }
    : enlace.conexion_plc === 'CONECTADO' ? { texto: 'CONECTADO', sev: 'normal' } : { texto: enlace.conexion_plc ?? 'SIN DATO', sev: 'alarma' },
  filas: [{ k: 'Enlace', v: detalle }],
});

const selectorEstado = (remoto: number | null, local: number | null): Lectura => ({
  estado: remoto === null && local === null ? { texto: 'SIN DATO', sev: 'inactivo' }
    : (remoto ?? 0) >= 0.5 ? { texto: 'REMOTO', sev: 'activo' }
    : (local ?? 0) >= 0.5 ? { texto: 'LOCAL', sev: 'aviso' } : { texto: 'EN 0', sev: 'inactivo' },
  filas: [],
});

/* ------------------------------------------------------------------ caudal MCC-09 (S7-200) */
const caudal: Fn = (id, variables, V, enlace, diag) => {
  const n = (k: string) => valorNum(V, k);
  const bomba = n('estado/sistema_funcionando');
  const remoto = n('estado/selector_remoto');
  const local = n('estado/selector_local');
  switch (id) {
    case 'bomba': {
      const var_ = n('actuadores/variador_pct');
      const disparo = diag?.hallazgos_secundarios?.some((h) => h.hallazgo === 'PARADA_TRAS_SATURACION');
      return {
        estado: bomba === null ? { texto: 'SIN DATO', sev: 'inactivo' }
          : bomba >= 0.5 ? { texto: 'EN MARCHA', sev: 'activo' }
          : { texto: disparo ? 'DETENIDA · posible disparo' : 'DETENIDA', sev: disparo ? 'alarma' : 'inactivo' },
        filas: [{ k: 'Velocidad (consigna)', v: fmtNum(var_, 0), u: '%' }],
      };
    }
    case 'variador': {
      const v = pct(n('actuadores/variador_pct'));
      return {
        barra: v === null ? undefined : { pct: v, sev: v >= 99 ? 'aviso' : 'normal', etiqueta: `${fmtNum(v, 1)} %` },
        estado: v !== null && v >= 99 && (bomba ?? 0) >= 0.5 ? { texto: 'SATURADO', sev: 'aviso' } : undefined,
        filas: [{ k: 'Mando', v: (local ?? 0) >= 0.5 ? 'Potenciómetro' : 'Salida PID' }],
      };
    }
    case 'valvula': {
      const v = pct(n('actuadores/valvula_pct'));
      return { barra: v === null ? undefined : { pct: v, sev: 'normal', etiqueta: `${fmtNum(v, 0)} % abierta` }, filas: [] };
    }
    case 'linea':
      return {
        principal: { valor: fmtNum(n('caudal/pv_pid'), 1), unidad: 'L/min' },
        filas: [{ k: 'Setpoint', v: fmtNum(n('caudal/setpoint_pid'), 1), u: 'L/min' }],
      };
    case 'caudalimetro': {
      const q = n('caudal/caudalimetro');
      const pv = n('caudal/pv_pid');
      const dif = q !== null && pv !== null ? pv - q : null;
      return {
        principal: { valor: fmtNum(q, 1), unidad: 'L/min' },
        estado: dif !== null && Math.abs(dif) > 3 && (bomba ?? 0) >= 0.5 ? { texto: 'NO COINCIDE CON PID', sev: 'alarma' } : undefined,
        filas: [
          { k: 'Crudo AIW0', v: fmtNum(n('caudal/caudalimetro_raw'), 0), u: 'cuentas' },
          { k: 'Δ vs PV del PID', v: fmtNum(dif, 2), u: 'L/min' },
        ],
      };
    }
    case 'pid': {
      const out = n('pid/salida');
      return {
        estado: (remoto ?? 0) < 0.5 ? { texto: 'SIN EFECTO (no remoto)', sev: 'inactivo' }
          : out !== null && out >= 99 ? { texto: 'SALIDA AL MÁXIMO', sev: 'aviso' } : { texto: 'REGULANDO', sev: 'activo' },
        filas: [
          { k: 'SP', v: fmtNum(n('caudal/setpoint_pid'), 1), u: 'L/min' },
          { k: 'PV', v: fmtNum(n('caudal/pv_pid'), 1), u: 'L/min' },
          { k: 'Salida', v: fmtNum(out, 1), u: '%' },
          { k: 'Kc · Ti', v: `${fmtNum(n('pid/kc'), 2)} · ${fmtNum(n('pid/ti'), 2)}`, u: 'min' },
        ],
      };
    }
    case 'tanque':
    case 'sensor_nivel': {
      const bajo = n('estado/nivel_bajo');
      const alto = n('estado/nivel_alto');
      return {
        estado: bajo === null ? { texto: 'SIN DATO', sev: 'inactivo' }
          : bajo >= 0.5 ? { texto: 'NIVEL BAJO', sev: 'alarma' }
          : (alto ?? 0) >= 0.5 ? { texto: 'NIVEL ALTO', sev: 'aviso' } : { texto: 'NIVEL NORMAL', sev: 'normal' },
        filas: [],
      };
    }
    case 'selector':
      return selectorEstado(remoto, local);
    case 'potenciometro':
      return {
        estado: (local ?? 0) >= 0.5 ? { texto: 'EN MANDO', sev: 'activo' } : { texto: 'SIN EFECTO', sev: 'inactivo' },
        filas: [{ k: 'Valor', v: fmtNum(n('actuadores/potenciometro'), 0), u: 'cuentas' }],
      };
    case 'pc_scada':
      return {
        estado: n('estado/modo_hmi_pc') === 0 ? { texto: 'FIJA EL SETPOINT', sev: 'activo' } : { texto: 'EN ESPERA', sev: 'inactivo' },
        filas: [{ k: 'Setpoint remoto', v: fmtNum(n('caudal/setpoint'), 1), u: 'L/min' }],
      };
    case 'hmi':
      return {
        estado: n('estado/modo_hmi_pc') === 1 ? { texto: 'FIJA EL SETPOINT', sev: 'activo' } : { texto: 'EN ESPERA', sev: 'inactivo' },
        filas: [{ k: 'Setpoint HMI', v: fmtNum(n('caudal/setpoint_hmi'), 1), u: 'L/min' }],
      };
    case 'plc':
      return plcEstado(enlace, 'CP243-1 · TSAP 11.00');
    case 'proteccion_motor': {
      const h = diag?.hallazgos_secundarios?.find((x) => x.hallazgo === 'PARADA_TRAS_SATURACION');
      return { estado: h ? { texto: 'POSIBLE DISPARO', sev: 'alarma' } : { texto: 'SIN SEÑAL AL PLC', sev: 'inactivo' }, filas: [] };
    }
    default:
      return generica(id, variables, V, enlace, diag);
  }
};

/* ------------------------------------------------------------------ nivel MCN-09 (MicroLogix 1100) */
const nivel: Fn = (id, variables, V, enlace, diag) => {
  const n = (k: string) => valorNum(V, k);
  const bomba = n('estado/bomba_marcha');
  const remoto = n('estado/selector_remoto');
  const local = n('estado/selector_local');
  const cm = n('nivel/cm');
  const saturado = (n('nivel/fuera_rango_sensor') ?? 0) >= 0.5;
  const hz = n('bomba/frecuencia_estimada_hz');
  const t1 = n('estado/tanque1_con_agua');
  const ev = (diag?.evidencia ?? {}) as Record<string, unknown>;
  switch (id) {
    case 'tanque_t2': {
      const p = cm === null ? null : pct((cm / 40) * 100);
      return {
        principal: { valor: fmtNum(cm, 1), unidad: 'cm' },
        estado: saturado ? { texto: 'SENSOR SATURADO', sev: 'alarma' }
          : cm !== null && cm > 35 ? { texto: 'SOBRE 35 cm', sev: 'aviso' } : undefined,
        barra: p === null ? undefined : { pct: p, sev: cm !== null && cm > 35 ? 'aviso' : 'normal', etiqueta: `${fmtNum(cm, 1)} de 40 cm medibles` },
        filas: [
          { k: 'Tendencia', v: fmtNum(ev.pendiente_cm_min, 1), u: 'cm/min' },
          { k: 'Caudal neto (est.)', v: fmtNum(ev.caudal_neto_estimado_l_min, 1), u: 'L/min' },
        ],
      };
    }
    case 'sensor_ultrasonico':
      return {
        estado: saturado ? { texto: 'SATURADO (>40 cm)', sev: 'alarma' } : cm === null ? { texto: 'SIN DATO', sev: 'inactivo' } : { texto: 'MIDIENDO', sev: 'normal' },
        filas: [
          { k: 'N7:4', v: fmtNum(n('nivel/raw'), 0), u: 'cuentas' },
          { k: 'Calibración', v: '(16348 − N7:4)/400' },
        ],
      };
    case 'tanque_t1':
    case 'interruptor_nivel_t1': {
      const alto = n('estado/mando_i03');
      return {
        estado: t1 === null ? { texto: 'SIN DATO', sev: 'inactivo' }
          : t1 < 0.5 ? { texto: 'NIVEL BAJO', sev: 'alarma' }
          : (alto ?? 0) >= 0.5 ? { texto: 'NIVEL ALTO (I:0/3)', sev: 'aviso' } : { texto: 'CON AGUA', sev: 'normal' },
        filas: id === 'interruptor_nivel_t1'
          ? [{ k: 'Bajo · I:0/2', v: t1 === null ? '—' : t1 >= 0.5 ? 'cubierto' : 'ACTIVADO' }, { k: 'Alto · I:0/3 (hip.)', v: alto === null ? '—' : alto >= 0.5 ? 'ACTIVADO' : 'libre' }]
          : [{ k: 'Capacidad', v: '78', u: 'L' }],
      };
    }
    case 'bomba':
      return {
        estado: bomba === null ? { texto: 'SIN DATO', sev: 'inactivo' }
          : bomba >= 0.5 ? { texto: 'EN MARCHA', sev: 'activo' }
          : { texto: t1 !== null && t1 < 0.5 ? 'DETENIDA · T1 bajo' : 'DETENIDA', sev: t1 !== null && t1 < 0.5 ? 'alarma' : 'inactivo' },
        filas: [{ k: 'Frecuencia (est.)', v: fmtNum(hz, 1), u: 'Hz' }],
      };
    case 'variador': {
      const p = hz === null ? null : pct((hz / 60) * 100);
      return {
        barra: p === null ? undefined : { pct: p, sev: 'normal', etiqueta: `${fmtNum(hz, 1)} Hz (est.)` },
        filas: [{ k: 'Mando', v: (remoto ?? 0) >= 0.5 ? 'PID (sin HMI)' : (local ?? 0) >= 0.5 ? 'Potenciómetro' : '—' }],
      };
    }
    case 'potenciometro':
      return {
        estado: (local ?? 0) >= 0.5 ? { texto: 'EN MANDO', sev: 'activo' } : { texto: 'SIN EFECTO', sev: 'inactivo' },
        filas: [
          { k: 'I:1.5', v: fmtNum(n('bomba/potenciometro_raw'), 0), u: 'cuentas' },
          { k: '≈ frecuencia', v: fmtNum(hz, 1), u: 'Hz' },
        ],
      };
    case 'valvula': {
      const abre = (n('valvula/abriendo') ?? 0) >= 0.5;
      const cierra = (n('valvula/cerrando') ?? 0) >= 0.5;
      const t = n('valvula/t_apertura');
      return {
        estado: abre ? { texto: 'ABRIENDO', sev: 'activo' } : cierra ? { texto: 'CERRANDO', sev: 'activo' } : { texto: 'EN REPOSO', sev: 'inactivo' },
        barra: abre && t !== null ? { pct: pct((t / 35) * 100) ?? 0, sev: 'normal', etiqueta: `${fmtNum(t, 1)} de 35 s` } : undefined,
        filas: [],
      };
    }
    case 'pid':
      return {
        estado: (remoto ?? 0) >= 0.5 ? { texto: 'SIN SETPOINT (sin HMI)', sev: 'aviso' } : { texto: 'SIN EFECTO (LOCAL)', sev: 'inactivo' },
        filas: [
          { k: 'SP crudo · N7:5', v: fmtNum(n('pid/setpoint_a_raw'), 0) },
          { k: 'CV crudo · N7:14', v: fmtNum(n('pid/cv_raw'), 0) },
        ],
      };
    case 'selector':
      return selectorEstado(remoto, local);
    case 'pulsadores':
      return {
        estado: (bomba ?? 0) >= 0.5 ? { texto: 'BOMBA ARRANCADA', sev: 'activo' } : { texto: 'EN ESPERA', sev: 'inactivo' },
        filas: [{ k: 'ARRANQUE · I:0/4', v: (n('estado/pulsador_arranque') ?? 0) >= 0.5 ? 'pulsado' : 'libre' }],
      };
    case 'hmi':
      return { estado: { texto: 'SIN COMUNICACIÓN', sev: 'aviso' }, filas: [{ k: 'IP configurada', v: '192.168.1.110' }] };
    case 'plc':
      return plcEstado(enlace, 'EtherNet/IP · TCP 44818');
    default:
      return generica(id, variables, V, enlace, diag);
  }
};

const REGLAS: Record<string, Fn> = { 'caudal-mcc09': caudal, 'nivel-mcn09': nivel };

/** Que mostrar en cada nodo del grafo segun el equipo. Un equipo nuevo usa la lectura generica hasta tener reglas. */
export function lectura(equipo: string | undefined, id: string, variables: string[], V: Record<string, Valor>,
  enlace: Enlace | null, diag: Diagnostico | null): Lectura {
  return (REGLAS[equipo ?? ''] ?? generica)(id, variables, V, enlace, diag);
}
