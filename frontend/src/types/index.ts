export interface Equipment {
  id: string;
  name: string;
  controller: string;
  ip: string;
  variable: string;
  value: number;
  unit: string;
  setpoint: number;
  timestamp: string;
  status: string;
  deviation: number;
  alarm: boolean;
}

export interface HistorySample {
  id: string;
  variable: string;
  unit: string;
  value: number;
  ts: string;
}

export interface LevelDetail {
  equipmentId: string;
  name: string;
  controller: string;
  plcIp: string;
  plcStatus: string;
  mode: string;
  level: number;
  unit: string;
  setpoint: number;
  tankHeight: number;
  percent: number;
  pumpOn: boolean;
  vfdHz: number;
  vfdPercent: number;
  valveOpen: number;
  highAlarm: boolean;
  lowAlarm: boolean;
  timestamp: string;
}

export interface AgentTool {
  name: string;
  server: string;
  description: string;
}

export interface AgentCall {
  name: string;
  ok: boolean;
  ms: number;
  result: string;
}

export interface AgentReply {
  reply: string;
  agent: string;
  ts: string;
  tools: AgentCall[];
  mode?: 'llm' | 'rules';
  model?: string | null;
}

export interface AgentStatus {
  mode: 'llm' | 'rules';
  enabled: boolean;
  model: string;
  provider: string;
  scope: string;
}

export interface HealthInfo {
  status: string;
  service: string;
  timestamp: string;
}

export type LinkState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';
export type LoadState = 'loading' | 'ready' | 'error';

export interface SeriesPoint {
  t: number;
  v: number;
}

/** Valor publicado por el conector edge del MCN-09 (MQTT). */
export interface SenalValor {
  valor: unknown;
  unidad?: string | null;
  source?: string | null;
  tag?: string | null;
  ts?: string | null;
}

/**
 * Señales REALES del módulo de nivel (MQTT/UNS, conector edge ML1100).
 * `valores` está indexado por el sufijo del tópico bajo
 * uss/campus/lab-automatizacion/sl01la07/nivel-mcn09/funcional/
 */
export interface NivelSenales {
  mqtt: boolean;
  edge?: string | null;
  plc?: string | null;
  mensajes: number;
  ultimo?: string | null;
  heartbeat?: string | null;
  alturaCm?: number | null;
  temaBase?: string;
  valores?: Record<string, SenalValor>;
}

/** Misma envoltura UNS, aplicada al módulo de caudal. */
export type CaudalSenales = NivelSenales;

/** Señales reales del módulo de presión (cFP-2200 vía MQTT/UNS). */
export type PresionSenales = NivelSenales;

/** Señales reales del módulo de temperatura (Twido vía MQTT/UNS). */
export type TemperaturaSenales = NivelSenales;

/** Orden de control remoto (API /api/control + SignalR controlResultado). */
export interface ControlOrden {
  id: string;
  tipo: string;
  valor: number | null;
  parametro: string | null;
  unidad?: string | null;
  equipo?: string;
  comentario?: string | null;
  correlacion?: string | null;
  origen?: string | null;
  usuario: string;
  rol: string;
  modo: string;
  estado: string;
  motivo: string | null;
  expedida: string;
  expira: string;
  timeoutEn: string;
  actualizada: string | null;
  escrito?: boolean | null;
  valorEsperado?: number | null;
  valorLeido?: number | null;
}
