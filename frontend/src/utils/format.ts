export interface ModuleMeta {
  label: string;
  color: string;
  short: string;
}

const META: Record<string, ModuleMeta> = {
  'caudal-mcc09': { label: 'Caudal MCC-09', color: '#1e88e5', short: 'Caudal' },
  'nivel-mcn09': { label: 'Nivel MCN-09', color: '#43a047', short: 'Nivel' },
  'presion-mcp09': { label: 'Presión MCP-09', color: '#8e24aa', short: 'Presión' },
  'temp-mct09': { label: 'Temperatura MCT-09', color: '#e2412d', short: 'Temperatura' },
};

export function moduleMeta(id: string): ModuleMeta {
  return META[id] ?? { label: id, color: '#757575', short: id };
}

/** Banda de alarma usada por el backend: ±12 % de la consigna en los equipos. */
export function isAlarm(value: number, setpoint: number, tolerance = 0.12): boolean {
  return Math.abs(value - setpoint) > Math.max(1e-6, Math.abs(setpoint) * tolerance);
}

/**
 * El valor de un equipo solo es utilizable si la calidad del dato es buena.
 * Con el sensor de nivel saturado el backend publica 'sensor_fuera_de_rango' y el
 * valor en cm es el tope de la escala (artefacto), no una medida real.
 */
export function valorMedible(calidad?: string | null): boolean {
  return (calidad ?? 'buena') === 'buena';
}

/** Banda del tanque: alarma alta/baja al ±15 % de la consigna (misma regla que el backend).
 *  Sin consigna real (setpoint ≤ 0) no se evalúa: nunca se inventa una alarma. */
export function levelAlarms(level: number | null, setpoint: number) {
  if (level == null || !(setpoint > 0)) return { high: false, low: false };
  return { high: level >= setpoint * 1.15, low: level <= setpoint * 0.85 };
}

export function ageSeconds(now: number, iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.round((now - t) / 1000));
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) return 'sin fecha';
  if (seconds < 5) return 'ahora mismo';
  if (seconds < 60) return `hace ${seconds} s`;
  const min = Math.floor(seconds / 60);
  if (min < 60) return `hace ${min} min`;
  const horas = Math.floor(min / 60);
  if (horas < 48) return `hace ${horas} h`;
  return `hace ${Math.floor(horas / 24)} días`;
}

export function isStale(now: number, iso: string | null | undefined, limit = 15): boolean {
  const age = ageSeconds(now, iso);
  return age === null || age > limit;
}

export function timeOnly(iso: string | number): string {
  const d = typeof iso === 'string' ? new Date(iso) : new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--:--';
  return d.toLocaleTimeString('es-PE', { hour12: false });
}

export function dateOnly(iso: string | number): string {
  const d = typeof iso === 'string' ? new Date(iso) : new Date(iso);
  if (Number.isNaN(d.getTime())) return '----/--/--';
  return d.toLocaleDateString('es-PE');
}

export function num(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return Number(value).toFixed(decimals);
}

export function clamp(value: number, min = 0, max = 100): number {
  return Math.min(max, Math.max(min, value));
}
