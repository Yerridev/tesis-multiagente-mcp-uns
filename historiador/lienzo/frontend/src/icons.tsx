/* Simbolos propios, inspirados en la simbologia de instrumentacion (trazo simple, sin relleno de color). */
interface P {
  activo?: boolean;
  giro?: number; // segundos por vuelta (impulsor de la bomba)
}

const S = (props: { children: React.ReactNode }) => (
  <svg viewBox="0 0 40 40" width="34" height="34" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {props.children}
  </svg>
);

export function Icono({ id, tipo, activo, giro }: { id: string; tipo: string } & P) {
  switch (id) {
    case 'tanque':
      return (
        <S>
          <path d="M9 9v22a11 3.5 0 0 0 22 0V9" />
          <ellipse cx="20" cy="9" rx="11" ry="3.5" />
          <path d="M9 22c4 1.8 18 1.8 22 0" strokeDasharray="2 2" />
        </S>
      );
    case 'bomba':
      return (
        <S>
          <circle cx="20" cy="20" r="12" />
          <g style={activo && giro ? { transformOrigin: '20px 20px', animation: `girar ${giro}s linear infinite` } : undefined}>
            <path d="M20 20l0-8M20 20l7 4M20 20l-7 4" />
          </g>
          <path d="M8 34h24" />
        </S>
      );
    case 'variador':
      return (
        <S>
          <rect x="7" y="8" width="26" height="24" rx="3" />
          <path d="M11 22c2-6 4-6 6 0s4 6 6 0 4-6 6 0" />
          <path d="M11 13h8" />
        </S>
      );
    case 'valvula':
      return (
        <S>
          <path d="M7 12v16l13-8zM33 12v16l-13-8z" />
          <path d="M20 20V9M15 9h10" />
        </S>
      );
    case 'linea':
      return (
        <S>
          <path d="M5 16h30M5 24h30" />
          <path d="M14 20h12M22 17l4 3-4 3" />
        </S>
      );
    case 'caudalimetro':
      return (
        <S>
          <circle cx="20" cy="20" r="11" />
          <path d="M14 23l6-6 6 6" />
          <path d="M4 20h5M31 20h5" />
        </S>
      );
    case 'sensor_nivel':
      return (
        <S>
          <circle cx="20" cy="15" r="7" />
          <path d="M20 22v10M14 32h12M17 15h6" />
        </S>
      );
    case 'pid':
      return (
        <S>
          <rect x="6" y="10" width="28" height="20" rx="10" />
          <path d="M12 23v-6h3a2 2 0 0 1 0 4h-3M20 17v6M25 17v6h2a3 3 0 0 0 0-6z" strokeWidth="1.5" />
        </S>
      );
    case 'plc':
      return (
        <S>
          <rect x="9" y="9" width="22" height="22" rx="2" />
          <path d="M13 5v4M20 5v4M27 5v4M13 31v4M20 31v4M27 31v4M5 14h4M5 26h4M31 14h4M31 26h4" />
          <rect x="15" y="15" width="10" height="10" rx="1" />
        </S>
      );
    case 'selector':
      return (
        <S>
          <circle cx="20" cy="20" r="11" />
          <path d={activo ? 'M20 20l7-7' : 'M20 20l-7-7'} strokeWidth="2.6" />
          <path d="M11 9l-2-2M29 9l2-2" />
        </S>
      );
    case 'potenciometro':
      return (
        <S>
          <circle cx="20" cy="21" r="9" />
          <path d="M20 21V13" strokeWidth="2.4" />
          <path d="M9 31a14 14 0 0 1 0-20M31 11a14 14 0 0 1 0 20" strokeDasharray="2 3" />
        </S>
      );
    case 'pc_scada':
      return (
        <S>
          <rect x="6" y="8" width="28" height="19" rx="2" />
          <path d="M15 33h10M20 27v6M10 22l5-5 4 3 6-7 5 4" />
        </S>
      );
    case 'hmi':
      return (
        <S>
          <rect x="7" y="7" width="26" height="26" rx="3" />
          <rect x="11" y="11" width="18" height="12" rx="1" />
          <circle cx="14" cy="28" r="1.5" />
          <circle cx="20" cy="28" r="1.5" />
          <circle cx="26" cy="28" r="1.5" />
        </S>
      );
    case 'proteccion_motor':
      return (
        <S>
          <path d="M20 5l12 5v9c0 8-5 13-12 16-7-3-12-8-12-16v-9z" />
          <path d="M21 12l-5 9h6l-3 8" />
        </S>
      );
    default:
      return (
        <S>
          <rect x="8" y="8" width="24" height="24" rx={tipo === 'control' ? 12 : 4} />
        </S>
      );
  }
}

export const IcoEditar = () => (
  <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 16l1-4 8-8 3 3-8 8zM11 6l3 3" /></svg>
);
export const IcoSol = () => (
  <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="10" cy="10" r="3.5" /><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4" /></svg>
);
export const IcoLuna = () => (
  <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M15.5 12.5A6.5 6.5 0 0 1 7.5 4.5a6.5 6.5 0 1 0 8 8z" /></svg>
);
export const IcoCandado = () => (
  <svg viewBox="0 0 20 20" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="4.5" y="9" width="11" height="8" rx="1.5" /><path d="M7 9V6.5a3 3 0 0 1 6 0V9" /></svg>
);
export const IcoPlay = () => (
  <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor"><path d="M6 4l10 6-10 6z" /></svg>
);
export const IcoPausa = () => (
  <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor"><rect x="5" y="4" width="3.5" height="12" rx="1" /><rect x="11.5" y="4" width="3.5" height="12" rx="1" /></svg>
);
export const IcoEnviar = () => (
  <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 10l14-6-5 13-2-5z" /></svg>
);
