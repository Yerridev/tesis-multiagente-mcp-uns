import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/* ============================================================
   Emergente único del sistema (reemplaza window.confirm / alert)
   ┌──────────────────────────────────────────┐
   │ TÍTULO · subtítulo                  [ × ]│
   ├──────────────────────────────────────────┤
   │ cuerpo                                    │
   ├──────────────────────────────────────────┤
   │ pie: texto (notificación) o botones       │
   └──────────────────────────────────────────┘
   Esc o clic fuera cierra (salvo `bloqueado`).
   ============================================================ */

interface Props {
  abierto: boolean;
  titulo: string;
  subtitulo?: string;
  onCerrar: () => void;
  children: ReactNode;
  /** Texto (notificación) o botones (acción). */
  pie?: ReactNode;
  tono?: 'normal' | 'peligro' | 'aviso';
  ancho?: number;
}

export function Emergente({ abierto, titulo, subtitulo, onCerrar, children, pie, tono = 'normal', ancho = 520 }: Props) {
  useEffect(() => {
    if (!abierto) return;
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onCerrar(); };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [abierto, onCerrar]);
  if (!abierto) return null;
  return createPortal(
    <div className="em-fondo" role="dialog" aria-modal="true" aria-label={titulo} onMouseDown={onCerrar}>
      <div className={`em-caja em-caja--${tono}`} style={{ width: `min(${ancho}px, 100%)` }} onMouseDown={(e) => e.stopPropagation()}>
        <header className="em-head">
          <div>
            <b>{titulo}</b>
            {subtitulo && <small>{subtitulo}</small>}
          </div>
          <button type="button" className="em-x" aria-label="Cerrar" onClick={onCerrar}>×</button>
        </header>
        <div className="em-cuerpo">{children}</div>
        {pie != null && <footer className="em-pie">{pie}</footer>}
      </div>
    </div>,
    document.body,
  );
}

export interface Condicion { etiqueta: string; valor: string; ok?: boolean | null }

/** Confirmación de Iniciar / Detener (los 4 módulos, planta real o simulada). */
export function ConfirmarOrden({ abierto, accion, equipo, condiciones, efecto, simulada, onCancelar, onConfirmar }: {
  abierto: boolean;
  accion: 'Iniciar' | 'Detener';
  equipo: string;
  condiciones: Condicion[];
  /** Qué hace la orden en el PLC (p. ej. "escribe M0.2 = 1 y arranca la bomba"). */
  efecto: string;
  simulada: boolean;
  onCancelar: () => void;
  onConfirmar: () => void;
}) {
  const iniciar = accion === 'Iniciar';
  return (
    <Emergente
      abierto={abierto}
      titulo={iniciar ? 'Confirmar inicio' : 'Confirmar detención'}
      subtitulo={`${equipo} · planta ${simulada ? 'simulada' : 'REAL'}`}
      tono={simulada ? 'aviso' : 'peligro'}
      onCerrar={onCancelar}
      pie={<>
        <button type="button" className="em-btn" onClick={onCancelar}>Cancelar</button>
        <button type="button" className={`em-btn ${iniciar ? 'em-btn--ok' : 'em-btn--peligro'}`} autoFocus onClick={onConfirmar}>
          {iniciar ? 'Iniciar' : 'Detener'}
        </button>
      </>}
    >
      <p className="em-sub">Condiciones verificadas antes de enviar</p>
      <ul className="em-cond">
        {condiciones.map((c) => (
          <li key={c.etiqueta}>
            <i className={c.ok == null ? '' : c.ok ? 'ok' : 'mal'} />
            <span>{c.etiqueta}</span>
            <b>{c.valor}</b>
          </li>
        ))}
      </ul>
      <p className={`em-alerta ${simulada ? 'em-alerta--aviso' : 'em-alerta--peligro'}`}>
        {simulada
          ? <>PLANTA SIMULADA: la orden {efecto} en el <b>PLC virtual</b>. No toca equipos físicos.</>
          : <>PLANTA REAL: la orden {efecto} en el <b>PLC físico</b>. El equipo se moverá de verdad.</>}
      </p>
    </Emergente>
  );
}
