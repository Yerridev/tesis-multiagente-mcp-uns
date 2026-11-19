import { useSyncExternalStore } from 'react';

/** Roles de la plataforma (de menor a mayor). */
export type Rol = 'viewer' | 'operador' | 'supervisor' | 'admin';
export const ROLES: Rol[] = ['viewer', 'operador', 'supervisor', 'admin'];
export const ROL_TEXTO: Record<Rol, string> = {
  viewer: 'Observador',
  operador: 'Operador',
  supervisor: 'Supervisor',
  admin: 'Administrador',
};
export const ROL_DESCRIPCION: Record<Rol, string> = {
  viewer: 'Solo mira: SCADA, lienzos, historial y agentes',
  operador: 'Además: Iniciar / Detener y llaves de la planta simulada',
  supervisor: 'Además: setpoints, PID, válvulas y todos los chats',
  admin: 'Además: usuarios e historial de accesos',
};

export function alMenos(rol: string | undefined | null, minimo: Rol): boolean {
  return ROLES.indexOf((rol ?? '') as Rol) >= ROLES.indexOf(minimo);
}

export interface SesionUsuario {
  token: string;
  usuario: string;
  nombre: string;
  rol: Rol;
  expira: string;
}

const CLAVE = 'mcp.auth';
const oyentes = new Set<() => void>();
let actual: SesionUsuario | null = leer();
/** false = el backend no exige login (backend local sin base): se usan las claves dev-… */
let authHabilitada = true;

function leer(): SesionUsuario | null {
  try {
    const s = JSON.parse(localStorage.getItem(CLAVE) ?? 'null') as SesionUsuario | null;
    if (!s?.token || new Date(s.expira).getTime() <= Date.now()) return null;
    return s;
  } catch {
    return null;
  }
}

function avisar() {
  oyentes.forEach((f) => f());
}

export function sesionActual(): SesionUsuario | null {
  if (actual && new Date(actual.expira).getTime() <= Date.now()) cerrarLocal();
  return actual;
}

export function tokenSesion(): string | null {
  return sesionActual()?.token ?? null;
}

export function autenticacionHabilitada(): boolean {
  return authHabilitada;
}

export function fijarAutenticacion(habilitada: boolean) {
  authHabilitada = habilitada;
  avisar();
}

export function guardarSesion(s: SesionUsuario) {
  actual = s;
  try {
    localStorage.setItem(CLAVE, JSON.stringify(s));
  } catch {
    /* sin almacenamiento: la sesión dura lo que la pestaña */
  }
  avisar();
}

export function cerrarLocal() {
  actual = null;
  try {
    localStorage.removeItem(CLAVE);
  } catch {
    /* nada */
  }
  avisar();
}

function suscribir(f: () => void) {
  oyentes.add(f);
  return () => oyentes.delete(f);
}

/** Usuario conectado (null = sin sesión). Se actualiza al entrar/salir. */
export function useUsuario(): SesionUsuario | null {
  return useSyncExternalStore(suscribir, sesionActual, sesionActual);
}

/** Rol efectivo: el de la sesión; sin autenticación habilitada, admin (modo desarrollo). */
export function useRol(): Rol {
  const s = useUsuario();
  useSyncExternalStore(suscribir, autenticacionHabilitada, autenticacionHabilitada);
  return s?.rol ?? (authHabilitada ? 'viewer' : 'admin');
}

const MENSAJES: Record<string, string> = {
  CREDENCIALES_INVALIDAS: 'Usuario o contraseña incorrectos',
  CREDENCIALES_INCOMPLETAS: 'Escribe usuario y contraseña',
  USUARIO_DESACTIVADO: 'Tu usuario está desactivado. Habla con el administrador',
  DEMASIADOS_INTENTOS: 'Demasiados intentos fallidos. Espera 10 minutos',
  SEGURIDAD_NO_DISPONIBLE: 'La base de datos de usuarios no responde (¿TimescaleDB levantado?)',
};

export async function iniciarSesion(usuario: string, password: string): Promise<string | null> {
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, password }),
    });
    const datos = (await res.json().catch(() => ({}))) as Partial<SesionUsuario> & { error?: string };
    if (!res.ok || !datos.token) return MENSAJES[datos.error ?? ''] ?? `No se pudo entrar (HTTP ${res.status})`;
    guardarSesion(datos as SesionUsuario);
    return null;
  } catch {
    return 'El backend no responde';
  }
}

export async function cerrarSesion() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch {
    /* igual se cierra en el navegador */
  }
  cerrarLocal();
}

/* Todas las llamadas a /api y /hubs del mismo origen llevan el token de la sesión. Si el backend
   responde 401 (sesión vencida, revocada o usuario desactivado) se vuelve al login. */
let instalado = false;
export function instalarFetchConSesion() {
  if (instalado || typeof window === 'undefined') return;
  instalado = true;
  const original = window.fetch.bind(window);
  window.fetch = async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof entrada === 'string' ? entrada : entrada instanceof URL ? entrada.pathname : entrada.url;
    const ruta = url.startsWith(window.location.origin) ? url.slice(window.location.origin.length) : url;
    const propia = ruta.startsWith('/api') || ruta.startsWith('/hubs');
    const token = tokenSesion();
    if (!propia || !token) return original(entrada, init);
    const cabeceras = new Headers(init?.headers ?? (entrada instanceof Request ? entrada.headers : undefined));
    const traiaDev = /^Bearer dev-/i.test(cabeceras.get('Authorization') ?? '');
    if (!cabeceras.has('Authorization') || traiaDev) cabeceras.set('Authorization', `Bearer ${token}`);
    const res = await original(entrada, { ...init, headers: cabeceras });
    if (res.status === 401 && !ruta.startsWith('/api/auth/login')) cerrarLocal();
    return res;
  };
}
