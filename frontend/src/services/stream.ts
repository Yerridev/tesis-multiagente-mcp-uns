import { tokenSesion } from './auth';

/**
 * Canal de telemetría en vivo.
 *
 * Sustituye al hub SSE del backend ASP.NET por **Server-Sent Events**:
 * el backend empuja los eventos (`telemetry`, `nivelSenales`, `controlResultado`…)
 * por una conexión HTTP que el navegador mantiene abierta con `EventSource`.
 *
 * El hub original era de solo push (el frontend nunca invocaba métodos del
 * servidor), así que SSE cubre exactamente el mismo caso con menos piezas y
 * reconexión automática incluida.
 */
export const STREAM_URL = '/api/stream';

export type ManejadorStream = (datos: unknown) => void;

/**
 * Abre el canal y entrega cada evento al manejador que le corresponde.
 *
 * `EventSource` no puede mandar cabeceras, así que el token de sesión viaja en
 * el query `?access_token=` (el backend lo acepta en /api y /hubs).
 */
export function createStream(manejadores: Record<string, ManejadorStream>): EventSource {
  const token = tokenSesion();
  const url = token
    ? `${STREAM_URL}?access_token=${encodeURIComponent(token)}`
    : STREAM_URL;

  const source = new EventSource(url);

  for (const [evento, manejador] of Object.entries(manejadores)) {
    source.addEventListener(evento, (ev) => {
      try {
        manejador(JSON.parse((ev as MessageEvent).data));
      } catch {
        /* dato ilegible: se ignora este evento */
      }
    });
  }

  return source;
}
