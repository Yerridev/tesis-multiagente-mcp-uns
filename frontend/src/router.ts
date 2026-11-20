import { useCallback, useEffect, useState } from 'react';

export type Route =
  | 'dashboard'
  | 'monitor'
  | 'agents'
  | 'mcp'
  | 'arch-physical'
  | 'arch-logical'
  | 'mod-caudal'
  | 'mod-nivel'
  | 'mod-presion'
  | 'mod-temp'
  | 'history'
  | 'reports'
  | 'status'
  | 'config'
  | 'usuarios'
  | 'nivel'
  | 'lienzo-planta'
  | 'lienzo-caudal'
  | 'lienzo-nivel'
  | 'lienzo-presion'
  | 'lienzo-temp';

export interface NavItem {
  kind: 'item';
  id: Route;
  label: string;
  icon: string;
  /** rol mínimo para verla en el menú */
  rol?: 'operador' | 'supervisor' | 'admin';
}

export interface NavGroup {
  kind: 'group';
  key: string;
  label: string;
  icon: string;
  children: Array<{ id: Route; label: string; icon: string }>;
}

export interface NavSection {
  header: string;
  entries: Array<NavItem | NavGroup>;
}

const item = (id: Route, label: string, icon: string): NavItem => ({ kind: 'item', id, label, icon });

/** Navegación idéntica a la del frontend original MCP-INDUSTRIAL. */
export const NAV: NavSection[] = [
  {
    header: 'Principal',
    entries: [
      item('dashboard', 'Dashboard', 'grid'),
      item('agents', 'Agentes de IA', 'robot'),
      {
        kind: 'group',
        key: 'lienzos',
        label: 'Lienzos',
        icon: 'canvas',
        children: [
          { id: 'lienzo-planta', label: 'Vista general', icon: 'grid' },
          { id: 'lienzo-caudal', label: 'Control de caudal', icon: 'flow' },
          { id: 'lienzo-nivel', label: 'Control de nivel', icon: 'tank' },
          { id: 'lienzo-presion', label: 'Control de presión', icon: 'gauge' },
          { id: 'lienzo-temp', label: 'Control de temperatura', icon: 'thermometer' },
        ],
      },
    ],
  },
  {
    header: 'Arquitectura',
    entries: [
      item('arch-logical', 'Arquitectura lógica', 'topology'),
    ],
  },
  {
    header: 'Industrial',
    entries: [
      {
        kind: 'group',
        key: 'modules',
        label: 'Módulos de control',
        icon: 'plantas',
        children: [
          { id: 'mod-caudal', label: 'Scada Caudal', icon: 'flow' },
          { id: 'mod-nivel', label: 'Scada Nivel', icon: 'tank' },
          { id: 'mod-presion', label: 'Scada Presión', icon: 'gauge' },
          { id: 'mod-temp', label: 'Scada Temperatura', icon: 'thermometer' },
        ],
      },
      item('history', 'Historial de mediciones', 'clock'),
      item('reports', 'Reportes', 'bars'),
    ],
  },
  {
    header: 'Sistema',
    entries: [
      item('status', 'Estado del sistema', 'chart'),
      { ...item('usuarios', 'Usuarios y accesos', 'users'), rol: 'admin' },
      item('config', 'Configuración', 'settings'),
    ],
  },
];

const TITLES: Record<Route, { title: string; subtitle: string }> = {
  dashboard: { title: 'Dashboard', subtitle: 'Resumen de la planta en tiempo real' },
  monitor: { title: 'Monitoreo en tiempo real', subtitle: 'Flujo en vivo · series de los módulos' },
  agents: { title: 'Agentes de IA', subtitle: 'Asistente con IA real · herramientas de solo lectura' },
  mcp: { title: 'Servidores MCP', subtitle: 'Orígenes de datos y herramientas del agente' },
  'arch-physical': { title: 'Arquitectura física', subtitle: 'Topología de red · PLCs · HMI · servidor' },
  'arch-logical': { title: 'Arquitectura lógica', subtitle: 'Flujo MQTT · PostgreSQL · API · agentes' },
  'mod-caudal': { title: 'Scada de Caudal', subtitle: 'Siemens S7-200 CPU226 · 192.168.114.7 · solo lectura' },
  'mod-nivel': { title: 'Scada de Nivel', subtitle: 'Allen-Bradley MicroLogix 1100 · 192.168.114.9 · solo lectura' },
  'mod-presion': { title: 'Scada de Presión', subtitle: 'Línea de presión · sensores' },
  'mod-temp': { title: 'Scada de Temperatura', subtitle: 'Línea de temperatura · sensores' },
  history: { title: 'Historial de mediciones', subtitle: 'Búfer de telemetría del backend FastAPI' },
  reports: { title: 'Reportes', subtitle: 'Resumen estadístico por módulo' },
  status: { title: 'Estado del sistema', subtitle: 'Verificación en vivo' },
  config: { title: 'Configuración', subtitle: 'Parámetros de la plataforma' },
  usuarios: { title: 'Usuarios y accesos', subtitle: 'Cuentas, roles e historial de entradas · solo administrador' },
  nivel: { title: 'Módulo de Nivel · MCN-09', subtitle: 'SCADA completo · solo lectura' },
  'lienzo-planta': { title: 'Lienzo · Vista general', subtitle: 'USS Chiclayo · Laboratorio de Automatización y Simulación de Procesos · aula SL01LA07' },
  'lienzo-caudal': { title: 'Lienzo de caudal · MCC-09/002', subtitle: 'Siemens S7-200 CPU226 + CP243-1 · 192.168.114.7 · solo lectura' },
  'lienzo-nivel': { title: 'Lienzo de nivel · MCN-09/001', subtitle: 'Allen-Bradley MicroLogix 1100 · 192.168.114.9 · solo lectura' },
  'lienzo-presion': { title: 'Lienzo de presión · MCP-09/001', subtitle: 'NI Compact FieldPoint cFP-2200 · 192.168.114.8 · solo lectura' },
  'lienzo-temp': { title: 'Lienzo de temperatura · MCT-09/001', subtitle: 'Schneider Twido TWDLCAE40DRF · 192.168.114.10 · solo lectura' },
};

export const NAV_ROUTES: Route[] = NAV.flatMap((section) =>
  section.entries.flatMap((entry) => (entry.kind === 'group' ? entry.children.map((c) => c.id) : [entry.id])),
);

export function routeDef(route: Route) {
  return TITLES[route] ?? TITLES.dashboard;
}

function parseHash(): Route {
  const raw = window.location.hash.replace(/^#\/?/, '').trim() as Route;
  return raw in TITLES ? raw : 'dashboard';
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(() =>
    typeof window === 'undefined' ? 'dashboard' : parseHash(),
  );

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = useCallback((next: Route) => {
    const hash = `#/${next}`;
    if (window.location.hash !== hash) window.location.hash = hash;
    setRoute(next);
  }, []);

  return [route, navigate];
}
