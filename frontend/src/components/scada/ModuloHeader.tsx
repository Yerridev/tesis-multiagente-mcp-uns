/* Cabecera del módulo SCADA: título, ficha del PLC, botón REAL/SIMULADOR y estado de comunicación. */
import { usePlantaModo } from './plantaSimulada';
export type Modo = 'real' | 'simulador';
export type EstadoCom = 'conectado' | 'sin-comunicacion' | 'reconectando';

const ESTADO_LABEL: Record<EstadoCom, string> = {
  conectado: 'PLC conectado',
  'sin-comunicacion': 'Sin comunicación',
  reconectando: 'Reconectando…',
};

interface Props {
  id: string;
  titulo: string;
  meta: string;
  estado: EstadoCom;
  modo: Modo;
  onModoChange: (modo: Modo) => void;
}

export function ModuloHeader({ id, titulo, meta, estado, modo, onModoChange }: Props) {
  const sim = modo === 'simulador';
  void onModoChange;   // ya no hay cambio de modo por página (ver abajo)
  const simulada = usePlantaModo() === 'simulado';   // backend con MODO_PLANTA=simulado
  const est: EstadoCom | 'simulado' = sim ? 'simulado' : estado;
  return (
    <header className={`mod-header mod-header--${est}`}>
      <div className="mod-header__info">
        <span className="mod-header__id">{id}</span>
        <h2 className="mod-header__title">{titulo}</h2>
        <p className="mod-header__meta">{sim ? 'Entrenamiento en el navegador · sin órdenes al PLC' : simulada ? 'PLANTA SIMULADA · simulador Python (mismo camino que el real: MQTT → backend → MCP)' : meta}</p>
      </div>
      <div className="mod-header__actions">
        {/* El modo de la planta es GLOBAL: lo fija el backend (MODO_PLANTA) con bat\04.0_SimularPlanta.bat /
            bat\04.1_DetenerSimulacion.bat. No hay botón por página: no se pierde al refrescar. */}
        <span className={`mode-btn mode-btn--${simulada ? 'simulador' : 'real'}`} title={simulada ? 'Planta simulada (simuladores Python)' : 'Laboratorio real'}>
          <span className="mode-btn__label">Planta</span>
          <span className="mode-btn__value">{simulada ? 'SIMULADA' : 'REAL'}</span>
        </span>
        <span className={`status-badge status-badge--${est}`}>
          <span className="status-badge__dot" />
          {sim ? 'Simulación activa' : ESTADO_LABEL[estado]}
        </span>
      </div>
    </header>
  );
}
