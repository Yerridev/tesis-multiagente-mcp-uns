import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import type { ConversacionCompleta, ConversacionResumen } from '../../types';
import { Emergente } from '../common/Emergente';
import { TextoMd } from './TextoMd';

const ORIGEN: Record<string, string> = { agentes: 'Agentes de IA', lienzo: 'Lienzo' };
const fecha = (iso: string) => new Date(iso).toLocaleString('es-PE', { hour12: false, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

/**
 * Historial de chats guardados (registros/conversaciones en la PC).
 * Lista las conversaciones, muestra cada una completa y permite continuarla.
 */
export function HistorialChats({ abierto, onCerrar, onContinuar }: {
  abierto: boolean;
  onCerrar: () => void;
  onContinuar?: (c: ConversacionCompleta) => void;
}) {
  const [lista, setLista] = useState<ConversacionResumen[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [abiertaConv, setAbiertaConv] = useState<ConversacionCompleta | null>(null);

  useEffect(() => {
    if (!abierto) return;
    setAbiertaConv(null); setError(null); setLista(null);
    api.conversaciones().then(setLista).catch((e) => setError(e instanceof Error ? e.message : 'No se pudo leer el historial'));
  }, [abierto]);

  const ver = (id: string) => api.conversacion(id).then(setAbiertaConv).catch(() => setError('No se pudo abrir la conversación'));

  return (
    <Emergente abierto={abierto} onCerrar={onCerrar} ancho={760}
      titulo={abiertaConv ? abiertaConv.titulo : 'Historial de chats'}
      subtitulo={abiertaConv ? `${ORIGEN[abiertaConv.origen.split(':')[0]] ?? abiertaConv.origen} · ${fecha(abiertaConv.creada)} · ${abiertaConv.mensajes.length} mensajes` : 'Conversaciones guardadas en registros/conversaciones'}
      pie={abiertaConv ? (
        <div className="hc-pie">
          <button type="button" className="hc-btn" onClick={() => setAbiertaConv(null)}>← Volver a la lista</button>
          {onContinuar ? <button type="button" className="hc-btn hc-btn--ok" onClick={() => { onContinuar(abiertaConv); onCerrar(); }}>Continuar esta conversación</button> : null}
        </div>
      ) : null}>
      {error ? <p className="hc-vacio">{error}</p> : null}
      {!abiertaConv ? (
        lista == null ? <p className="hc-vacio">Cargando…</p>
          : lista.length === 0 ? <p className="hc-vacio">Aún no hay conversaciones guardadas.</p>
          : (
            <ul className="hc-lista">
              {lista.map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => void ver(c.id)}>
                    <b>{c.titulo || '(sin título)'}</b>
                    <small>
                      {fecha(c.actualizada)} · {ORIGEN[c.origen.split(':')[0]] ?? c.origen}{c.origen.includes(':') ? ` ${c.origen.split(':')[1]}` : ''} · {c.mensajes} mensajes
                      {c.modelos.length ? ` · ${c.modelos.map((m) => m.split('/').pop()).join(', ')}` : ''}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          )
      ) : (
        <div className="hc-conv">
          {abiertaConv.mensajes.map((m, i) => (
            <div key={i} className={`hc-msg hc-msg--${m.rol}`}>
              <div className="hc-burbuja">{m.rol === 'user' ? m.texto : <TextoMd texto={m.texto} />}</div>
              <small>{new Date(m.ts).toLocaleTimeString('es-PE', { hour12: false })}{m.modelo ? ` · ${m.modelo.split('/').pop()}` : m.rol === 'agente' && m.modo === 'rules' ? ' · reglas' : ''}{m.ms ? ` · ${(m.ms / 1000).toFixed(1)} s` : ''}</small>
            </div>
          ))}
        </div>
      )}
    </Emergente>
  );
}
