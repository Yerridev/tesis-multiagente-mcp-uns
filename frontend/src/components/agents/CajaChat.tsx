import { useLayoutEffect, useRef, type ReactNode } from 'react';

/* ============================================================
   Caja para escribir al agente (todos los chats):
   ┌────────────────────────────────────────────┐
   │ texto que crece con lo que escribes…       │
   │ (hasta ~8 líneas, luego scroll propio)     │
   │                    [Modelo ▾]  [Enviar →]  │
   └────────────────────────────────────────────┘
   Enter envía · Shift+Enter hace un salto de línea.
   ============================================================ */

interface Props {
  valor: string;
  onCambio: (v: string) => void;
  onEnviar: () => void;
  placeholder: string;
  etiqueta: string;
  ocupado?: boolean;
  extras?: ReactNode;          // p. ej. el selector de modelo
  textoBoton?: ReactNode;
  className?: string;
}

export function CajaChat({ valor, onCambio, onEnviar, placeholder, etiqueta, ocupado, extras, textoBoton = 'Enviar', className = '' }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  /* crece con el texto: se mide el alto real y el CSS pone el tope (max-height) */
  useLayoutEffect(() => {
    const t = ref.current;
    if (!t) return;
    t.style.height = 'auto';
    t.style.height = `${t.scrollHeight}px`;
  }, [valor]);
  const puede = !ocupado && valor.trim().length > 0;
  return (
    <form className={`cc-caja nodrag nowheel ${className}`} onSubmit={(e) => { e.preventDefault(); if (puede) onEnviar(); }}>
      <textarea
        ref={ref}
        rows={1}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (puede) onEnviar();
          }
        }}
        placeholder={placeholder}
        aria-label={etiqueta}
      />
      <div className="cc-barra">
        <small className="cc-ayuda">Enter envía · Shift+Enter nueva línea</small>
        {extras}
        <button type="submit" className="cc-enviar" disabled={!puede}>{textoBoton}</button>
      </div>
    </form>
  );
}
