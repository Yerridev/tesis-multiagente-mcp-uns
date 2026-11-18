import type {
  AgentReply,
  ConversacionCompleta,
  ConversacionResumen,
  AgentStatus,
  AgentTool,
  CatalogoMcpRespuesta,
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

  /** servidores MCP reales del sistema multiagente (bat 31): herramientas publicadas y últimas llamadas */
  mcpCatalogo: () => request<CatalogoMcpRespuesta>('/api/mcp/catalogo'),

  agentStatus: () => request<AgentStatus>('/api/agent/status'),

  /** history: turnos previos de la conversación (para que el agente entienda "¿y ahora?") */
  agentAsk: (message: string, model?: string | null, history?: { rol: 'user' | 'agente'; texto: string }[],
    conv?: { id?: string | null; origen: string }) =>
    request<AgentReply>('/api/agent/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, model: model ?? undefined, history: history?.slice(-8),
        conversacionId: conv?.id ?? undefined, origen: conv?.origen }),
    }),

  /** Chats guardados con los agentes */
  conversaciones: () => request<ConversacionResumen[]>('/api/agent/conversaciones'),
  conversacion: (id: string) => request<ConversacionCompleta>(`/api/agent/conversaciones/${encodeURIComponent(id)}`),
};

export const HUB_URL = '/hubs/plant';
export const EQUIPMENT_IDS = ['caudal-mcc09', 'nivel-mcn09', 'presion-mcp09', 'temp-mct09'] as const;
export const LEVEL_ID = 'nivel-mcn09';
