/* Cabecera del módulo SCADA: título, ficha del PLC, botón REAL/SIMULADOR y estado de comunicación. */
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
  const est: EstadoCom | 'simulado' = sim ? 'simulado' : estado;
  return (
    <header className={`mod-header mod-header--${est}`}>
      <div className="mod-header__info">
        <span className="mod-header__id">{id}</span>
        <h2 className="mod-header__title">{titulo}</h2>
        <p className="mod-header__meta">{sim ? 'Datos simulados · sin órdenes al PLC' : meta}</p>
      </div>
      <div className="mod-header__actions">
        <button
          type="button"
          className={`mode-btn mode-btn--${modo}`}
          onClick={() => onModoChange(sim ? 'real' : 'simulador')}
          aria-pressed={sim}
          title={sim ? 'Volver a REAL' : 'Cambiar a SIMULADOR'}
        >
          <span className="mode-btn__label">Modo</span>
          <span className="mode-btn__value">{sim ? 'SIMULADOR' : 'REAL'}</span>
        </button>
        <span className={`status-badge status-badge--${est}`}>
          <span className="status-badge__dot" />
          {sim ? 'Simulación activa' : ESTADO_LABEL[estado]}
        </span>
      </div>
    </header>
  );
}
