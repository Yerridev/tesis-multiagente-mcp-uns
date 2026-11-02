import { useEffect, useRef, useState } from 'react';
import { usePlant } from '../../../context/PlantContext';
import { api } from '../../../services/api';
import type { AgentCall, AgentStatus } from '../../../types';

const SUGERENCIAS = ['Estado de la planta', '¿Hay alarmas?'];

/**
 * Agente dentro del lienzo (versión compacta del panel de la tesis):
 * usa el mismo endpoint /api/agent/ask (IA real vía OpenRouter si está configurada).
 */
export function AgentePanel() {
  const { equipment } = usePlant();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [consulta, setConsulta] = useState('');
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [respuesta, setRespuesta] = useState<string | null>(null);
  const [tools, setTools] = useState<AgentCall[]>([]);
  const [modelo, setModelo] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .agentStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [respuesta, ocupado]);

  const enviar = async (texto: string) => {
    const consulta = texto.trim();
    if (!consulta || ocupado) return;
    setMensaje(consulta);
    setRespuesta(null);
    setError(null);
    setOcupado(true);
    try {
      const reply = await api.agentAsk(consulta);
      setRespuesta(reply.reply);
      setTools(reply.tools);
      setModelo(reply.model ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo contactar con el agente.');
    } finally {
      setOcupado(false);
    }
  };

  const llm = status?.mode === 'llm';

  return (
    <div className="lz-agente">
      <div className="lz-agente-cab">
        <span className={`lz-chip-modo ${llm ? 'vivo' : 'hist'}`}>{llm ? 'IA ACTIVA' : 'REGLAS'}</span>
        <small>{llm ? status?.model : 'reglas de supervisión'}</small>
        <span className="lz-agente-eq">{equipment.length} equipos</span>
      </div>

      <div className="lz-agente-log" ref={logRef}>
        {!mensaje && !respuesta ? (
          <div className="lz-msg lz-msg-agente">
            Pregunta por el estado de la planta, las alarmas o el historial. Respuesta con los datos en vivo.
          </div>
        ) : null}
        {mensaje ? <div className="lz-msg lz-msg-user">{mensaje}</div> : null}
        {ocupado ? <div className="lz-msg lz-msg-agente">… consultando</div> : null}
        {!ocupado && respuesta ? (
          <div className="lz-msg lz-msg-agente">
            {respuesta}
            {modelo || tools.length ? (
              <div className="lz-msg-tools">
                {modelo ? <span className="tag tag-warn">{modelo}</span> : null}
                {tools.map((tool) => (
                  <span key={tool.name} className={`tag ${tool.ok ? 'tag-ok' : 'tag-err'}`}>
                    {tool.name} · {tool.ms} ms
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {!ocupado && error ? <div className="lz-msg lz-msg-err">{error}</div> : null}
      </div>

      <div className="lz-agente-sug">
        {SUGERENCIAS.map((s) => (
          <button key={s} type="button" className="lz-chip-btn" onClick={() => void enviar(s)} disabled={ocupado}>
            {s}
          </button>
        ))}
      </div>

      <form
        className="lz-agente-form"
        onSubmit={(event) => {
          event.preventDefault();
          const texto = consulta;
          setConsulta('');
          void enviar(texto);
        }}
      >
        <input
          value={consulta}
          onChange={(event) => setConsulta(event.target.value)}
          placeholder="Pregunta al agente…"
          aria-label="Consulta al agente del lienzo"
        />
        <button type="submit" className="btn" disabled={ocupado || !consulta.trim()}>
          Enviar
        </button>
      </form>
    </div>
  );
}
