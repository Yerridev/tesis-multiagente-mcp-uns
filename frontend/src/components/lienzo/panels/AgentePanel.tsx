import { useSesion } from '../../agents/useSesion';
import { useEffect, useRef, useState } from 'react';
import { usePlant } from '../../../context/PlantContext';
import { api } from '../../../services/api';
import type { AgentCall, AgentStatus } from '../../../types';
import { SelectorModelo, useModeloElegido } from '../../agents/SelectorModelo';
import { CajaChat } from '../../agents/CajaChat';
import { TextoMd } from '../../agents/TextoMd';

const SUGERENCIAS = ['Estado de la planta', '¿Hay alarmas?'];

/**
 * Agente dentro del lienzo (versión compacta del panel de la tesis):
 * usa el mismo endpoint /api/agent/ask (IA real vía OpenRouter si está configurada).
 */
export function AgentePanel() {
  const { equipment } = usePlant();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const ia = useModeloElegido(status);   // modelo elegido junto a Enviar
  const [consulta, setConsulta] = useState('');
  /* conversación completa (como el chat de Agentes de IA): se desplaza en el centro */
  type Turno = { id: number; rol: 'user' | 'agente' | 'err'; texto: string; tools?: AgentCall[]; modelo?: string | null };
  /* cada lienzo conserva su chat al cambiar de módulo o refrescar (se borra con Nuevo chat o al cerrar el navegador) */
  const claveChat = `mcp.chat.lienzo.${window.location.pathname}${window.location.hash}`;
  const [turnos, setTurnos] = useSesion<Turno[]>(`${claveChat}.turnos`, []);
  const [ocupado, setOcupado] = useState(false);
  const [convId, setConvId] = useSesion<string | null>(`${claveChat}.conversacion`, null);   // conversación guardada de este lienzo
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .agentStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [turnos, ocupado]);

  const enviar = async (texto: string) => {
    const consulta = texto.trim();
    if (!consulta || ocupado) return;
    const id = Date.now();
    setTurnos((t) => [...t, { id, rol: 'user', texto: consulta }]);
    setOcupado(true);
    try {
      const historial = turnos.filter((x) => x.rol !== 'err').map((x) => ({ rol: x.rol === 'user' ? ('user' as const) : ('agente' as const), texto: x.texto }));
      const reply = await api.agentAsk(consulta, ia.modelo, historial, { id: convId, origen: 'lienzo' });
      if (reply.conversacionId) setConvId(reply.conversacionId);
      setTurnos((t) => [...t, { id: id + 1, rol: 'agente', texto: reply.reply, tools: reply.tools, modelo: reply.model ?? null }]);
    } catch (err) {
      setTurnos((t) => [...t, { id: id + 1, rol: 'err', texto: err instanceof Error ? err.message : 'No se pudo contactar con el agente.' }]);
    } finally {
      setOcupado(false);
    }
  };

  const llm = status?.mode === 'llm';

  return (
    <div className="lz-agente">
      <div className="lz-agente-cab">
        <span className={`lz-chip-modo ${llm ? 'vivo' : 'hist'}`}>{llm ? 'IA ACTIVA' : 'REGLAS'}</span>
        <small>{llm ? (ia.actual?.nombre ?? status?.model) : 'reglas de supervisión'}</small>
        <span className="lz-agente-eq">{equipment.length} equipos</span>
      </div>

      <div className="lz-agente-log" ref={logRef}>
        <div className="lz-msg lz-msg-agente">
          Pregunta por el estado de la planta, las alarmas o el historial. Respuesta con los datos en vivo.
        </div>
        {turnos.map((t) =>
          t.rol === 'user' ? <div key={t.id} className="lz-msg lz-msg-user">{t.texto}</div>
          : t.rol === 'err' ? <div key={t.id} className="lz-msg lz-msg-err">{t.texto}</div>
          : (
            <div key={t.id} className="lz-msg lz-msg-agente">
              <TextoMd texto={t.texto} />
              {t.modelo || t.tools?.length ? (
                <div className="lz-msg-tools">
                  {t.modelo ? <span className="tag tag-warn">{t.modelo}</span> : null}
                  {t.tools?.map((tool) => (
                    <span key={tool.name} className={`tag ${tool.ok ? 'tag-ok' : 'tag-err'}`}>
                      {tool.name} · {tool.ms} ms
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        {ocupado ? <div className="lz-msg lz-msg-agente">… consultando</div> : null}
      </div>

      {/* pie: sugerencias + caja para escribir (separado por una línea) */}
      <div className="lz-agente-pie">
      <div className="lz-agente-sug">
        {SUGERENCIAS.map((s) => (
          <button key={s} type="button" className="lz-chip-btn" onClick={() => void enviar(s)} disabled={ocupado}>
            {s}
          </button>
        ))}
        <button type="button" className="lz-chip-btn" style={{ marginLeft: 'auto' }} title="Empezar una conversación nueva"
          onClick={() => { setTurnos([]); setConvId(null); }} disabled={ocupado || turnos.length === 0}>
          Nuevo chat
        </button>
      </div>

      <CajaChat
        valor={consulta}
        onCambio={setConsulta}
        onEnviar={() => { const texto = consulta; setConsulta(''); void enviar(texto); }}
        placeholder="Pregunta al agente…"
        etiqueta="Consulta al agente del lienzo"
        ocupado={ocupado}
        extras={llm ? <SelectorModelo modelos={ia.modelos} valor={ia.modelo} onElegir={ia.elegir} disabled={ocupado} /> : null}
      />
      </div>
    </div>
  );
}
