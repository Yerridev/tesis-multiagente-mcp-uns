/** Cliente de la API de control (dry-run). El token por defecto es de desarrollo (rol supervisor). */

const BASE = '';

export const CONTROL_TOKEN_KEY = 'mcp.control.token';
export const CONTROL_TOKEN_DEFECTO = 'dev-supervisor';

export function tokenControl(): string {
  if (typeof localStorage === 'undefined') return CONTROL_TOKEN_DEFECTO;
  return localStorage.getItem(CONTROL_TOKEN_KEY) ?? CONTROL_TOKEN_DEFECTO;
}

export interface RespuestaControl<T> {
  ok: boolean;
  status: number;
  datos?: T;
  error?: string;
}

async function pedir<T>(path: string, init?: RequestInit): Promise<RespuestaControl<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${tokenControl()}`,
        ...(init?.headers ?? {}),
      },
    });
    const texto = await res.text();
    let datos: T | undefined;
    try {
      datos = texto ? (JSON.parse(texto) as T) : undefined;
    } catch {
      datos = undefined;
    }
    return { ok: res.ok, status: res.status, datos, error: res.ok ? undefined : ((datos as { error?: string } | undefined)?.error ?? `HTTP ${res.status}`) };
  } catch (e) {
    return { ok: false, status: 0, error: (e as Error).message };
  }
}

export interface EstadoControlDatos {
  modoEfectivo: string;
  realArmado: boolean;
  motivosReal: string[];
  configuracion: { modo: string; habilitadoEscritura: boolean; controlReal: string | null; timeoutSegundos: number; expiracionSegundos: number };
  proceso: { simulador: boolean; plc: string; selector: string | null; nivelBajoT1: boolean | null; mqttNivel: boolean; fuenteControl?: string | null };
  telemetria?: { ultimo: string | null; edadSegundos: number | null; fresca: boolean; maxSegundos: number };
  pendientes: number;
}

/** Devuelve usuario + datos del estado (/api/control/estado → { usuario, datos }). */
export async function controlEstado(): Promise<{
  ok: boolean;
  status: number;
  usuario?: string;
  datos?: EstadoControlDatos;
  error?: string;
}> {
  const r = await pedir<{ usuario?: string; datos: EstadoControlDatos }>('/api/control/estado');
  return { ok: r.ok, status: r.status, usuario: r.datos?.usuario, datos: r.datos?.datos, error: r.error };
}

export interface SolicitudControl {
  tipo: string;
  valor?: number | null;
  parametro?: string | null;
  unidad?: string | null;
  equipo?: string;
  comentario?: string | null;
  correlacion?: string | null;
  origen?: string | null;
}

export const enviarControl = (sol: SolicitudControl) =>
  pedir<Record<string, unknown>>('/api/control/nivel/comandos', {
    method: 'POST',
    body: JSON.stringify({ equipo: 'nivel-mcn09', origen: 'SCADA-WEB', ...sol }),
  });

export const listarOrdenes = () => pedir<import('../types').ControlOrden[]>('/api/control/nivel/comandos');

export const enviarControlCaudal = (sol: SolicitudControl) =>
  pedir<import('../types').ControlOrden>('/api/control/caudal/comandos', {
    method: 'POST',
    body: JSON.stringify({ equipo: 'caudal-mcc09', origen: 'SCADA-WEB', ...sol }),
  });

export const estadoControlCaudal = () =>
  pedir<{ usuario?: string; datos: { modoEfectivo: string; realArmado: boolean; proceso: { plc: string; selector: string; mqtt: boolean }; telemetria: { fresca: boolean } } }>('/api/control/caudal/estado');

export const listarOrdenesCaudal = () => pedir<import('../types').ControlOrden[]>('/api/control/caudal/comandos');

export const enviarControlPresion = (sol: SolicitudControl) =>
  pedir<import('../types').ControlOrden>('/api/control/presion/comandos', {
    method: 'POST',
    body: JSON.stringify({ equipo: 'presion-mcp09', origen: 'SCADA-WEB', ...sol }),
  });

export const estadoControlPresion = () =>
  pedir<{ usuario?: string; datos: { modoEfectivo: string; realArmado: boolean; proceso: { plc: string; selector: string; mqtt: boolean }; telemetria: { fresca: boolean } } }>('/api/control/presion/estado');

export const listarOrdenesPresion = () => pedir<import('../types').ControlOrden[]>('/api/control/presion/comandos');

/** Control protegido del MCT-09: el conector solo permite %M30 y %MW100. */
export const enviarControlTemperatura = (sol: SolicitudControl) =>
  pedir<import('../types').ControlOrden>('/api/control/temperatura/comandos', {
    method: 'POST',
    body: JSON.stringify({ equipo: 'temp-mct09', origen: 'SCADA-WEB', ...sol }),
  });

export const estadoControlTemperatura = () =>
  pedir<{ usuario?: string; datos: { modoEfectivo: string; realArmado: boolean; proceso: { plc: string; selector: string; fallaPrincipal: boolean | null; fallaEnfriador: boolean | null }; telemetria: { fresca: boolean }; pendientes: number } }>('/api/control/temperatura/estado');

export const listarOrdenesTemperatura = () => pedir<import('../types').ControlOrden[]>('/api/control/temperatura/comandos');
