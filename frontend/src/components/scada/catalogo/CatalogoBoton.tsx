import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ControlButton } from '@xyflow/react';
import { KeysModule } from './CatalogoComponentes';
import './catalogo.css';

/** Botón extra en los controles del mímico (+ / − / ⛶ / inventario) que abre el catálogo de piezas. */
export function CatalogoBoton() {
  const [abierto, setAbierto] = useState(false);
  useEffect(() => {
    if (!abierto) return;
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setAbierto(false); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [abierto]);

  return (
    <>
      <ControlButton onClick={() => setAbierto(true)} title="Catálogo de piezas" aria-label="Catálogo de piezas">
        {/* icono de inventario: caja con compartimentos */}
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ fill: 'none', maxWidth: 14, maxHeight: 14 }}>
          <path d="M3 7l9-4 9 4-9 4-9-4z" /><path d="M3 7v10l9 4 9-4V7" /><path d="M12 11v10" />
        </svg>
      </ControlButton>
      {abierto && createPortal(
        <div className="cat-modal" role="dialog" aria-modal="true" aria-label="Catálogo de piezas" onClick={() => setAbierto(false)}>
          <div className="cat-modal-caja" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="cat-cerrar" onClick={() => setAbierto(false)} aria-label="Cerrar">×</button>
            <KeysModule />
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
