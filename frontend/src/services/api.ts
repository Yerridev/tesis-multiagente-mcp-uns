import type {
  AgentReply,
  AgentStatus,
  AgentTool,
  Equipment,
  HealthInfo,
  HistorySample,
  LevelDetail,
  NivelSenales,
  CaudalSenales,
  PresionSenales,
  TemperaturaSenales,
} from '../types';

/** Misma origen que el documento: el frontend lo sirve el backend ASP.NET Core. */
const BASE = '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(`HTTP ${res.status} · ${path}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthInfo>('/api/health'),

  equipment: () => request<Equipment[]>('/api/equipment'),

  equipmentById: (id: string) => request<Equipment>(`/api/equipment/${encodeURIComponent(id)}`),

  history: (equipmentId?: string, limit = 600) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (equipmentId) params.set('equipmentId', equipmentId);
    return request<HistorySample[]>(`/api/history?${params.toString()}`);
  },

  levelDetail: () => request<LevelDetail>('/api/equipment/nivel-mcn09/detail'),

  /** Señales reales del módulo de nivel (MQTT/UNS, conector edge ML1100). */
  nivelSenales: () => request<NivelSenales>('/api/equipment/nivel-mcn09/signals'),

  caudalSenales: () => request<CaudalSenales>('/api/equipment/caudal-mcc09/signals'),

  /** Señales reales del módulo de presión (MQTT/UNS, conector edge cFP-2200 en la VM). */
  presionSenales: () => request<PresionSenales>('/api/equipment/presion-mcp09/signals'),

  /** Señales reales del módulo de temperatura (MQTT/UNS, conector edge Twido). */
  temperaturaSenales: () => request<TemperaturaSenales>('/api/equipment/temp-mct09/signals'),

  agentTools: () => request<AgentTool[]>('/api/agent/tools'),

  agentStatus: () => request<AgentStatus>('/api/agent/status'),

  agentAsk: (message: string) =>
    request<AgentReply>('/api/agent/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    }),
};

export const HUB_URL = '/hubs/plant';
export const EQUIPMENT_IDS = ['caudal-mcc09', 'nivel-mcn09', 'presion-mcp09', 'temp-mct09'] as const;
export const LEVEL_ID = 'nivel-mcn09';
