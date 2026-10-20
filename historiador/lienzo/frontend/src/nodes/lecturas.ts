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

const pct = (v: number | null) => (v === null ? null : Math.max(0, Math.min(100, v)));

export function lectura(id: string, variables: string[], V: Record<string, Valor>, enlace: Enlace | null,
  diag: Diagnostico | null): Lectura {
  const n = (k: string) => valorNum(V, k);
  const bomba = n('estado/sistema_funcionando');
  const remoto = n('estado/selector_remoto');
  const local = n('estado/selector_local');
  switch (id) {
    case 'bomba': {
      const var_ = n('actuadores/variador_pct');
      const disparo = diag?.hallazgos_secundarios.some((h) => h.hallazgo === 'PARADA_TRAS_SATURACION');
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
      return {
        barra: v === null ? undefined : { pct: v, sev: 'normal', etiqueta: `${fmtNum(v, 0)} % abierta` },
        filas: [],
      };
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
      return {
        estado: remoto === null ? { texto: 'SIN DATO', sev: 'inactivo' }
          : remoto >= 0.5 ? { texto: 'REMOTO', sev: 'activo' }
          : (local ?? 0) >= 0.5 ? { texto: 'LOCAL', sev: 'aviso' } : { texto: 'EN 0', sev: 'inactivo' },
        filas: [],
      };
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
      return {
        estado: !enlace ? { texto: 'HISTÓRICO', sev: 'inactivo' }
          : enlace.conexion_plc === 'CONECTADO' ? { texto: 'CONECTADO', sev: 'normal' } : { texto: enlace.conexion_plc ?? 'SIN DATO', sev: 'alarma' },
        filas: [{ k: 'Enlace', v: 'CP243-1 · TSAP 11.00' }],
      };
    case 'proteccion_motor': {
      const h = diag?.hallazgos_secundarios.find((x) => x.hallazgo === 'PARADA_TRAS_SATURACION');
      return {
        estado: h ? { texto: 'POSIBLE DISPARO', sev: 'alarma' } : { texto: 'SIN SEÑAL AL PLC', sev: 'inactivo' },
        filas: [],
      };
    }
    default:
      return { filas: variables.slice(0, 4).map((v) => ({ k: v.split('/').pop() ?? v, v: fmtNum(n(v), 2), u: V[v]?.unidad ?? '' })) };
  }
}
