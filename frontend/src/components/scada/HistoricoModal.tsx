/* Panel emergente «Histórico» (mismo que en Caudal), reutilizable por los 4 SCADA. */
interface Props {
  abierto: boolean;
  onClose: () => void;
  id: string;
  online: boolean;
  muestras: number;
  ultima: string;
  fuente: string;
}

export function HistoricoModal({ abierto, onClose, id, online, muestras, ultima, fuente }: Props) {
  if (!abierto) return null;
  return (
    <div className="co-modal" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="co-modal-caja co-hist" onClick={(e) => e.stopPropagation()}>
        <div className="co-modal-head"><b><i className={online ? 'co-hist-dot on' : 'co-hist-dot'}>●</i> Histórico · {id}</b><button onClick={onClose}>×</button></div>
        <dl className="co-modal-cuerpo co-hist-list">
          <dt>Tasa</dt><dd>1 segundo</dd>
          <dt>Muestras</dt><dd>{muestras}</dd>
          <dt>Última lectura</dt><dd className={online ? undefined : 'nodata'}>{online ? ultima : 'Sin datos'}</dd>
          <dt>Fuente</dt><dd>{fuente}</dd>
        </dl>
      </div>
    </div>
  );
}
