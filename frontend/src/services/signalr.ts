import { HubConnectionBuilder, HttpTransportType, LogLevel } from '@microsoft/signalr';
import { HUB_URL } from './api';
import { tokenSesion } from './auth';

/**
 * Conexión SignalR al hub /hubs/plant.
 * Es el canal único de telemetría en tiempo real: no se sustituye por sondeos.
 */
export function createConnection() {
  return new HubConnectionBuilder()
    .withUrl(HUB_URL, {
      transport: HttpTransportType.WebSockets | HttpTransportType.LongPolling,
      skipNegotiation: false,
      // el hub exige sesión: el token va en la negociación y en ?access_token= del WebSocket
      accessTokenFactory: () => tokenSesion() ?? '',
    })
    .withAutomaticReconnect([0, 1000, 2000, 5000, 10000, 30000])
    .configureLogging(LogLevel.Warning)
    .build();
}
