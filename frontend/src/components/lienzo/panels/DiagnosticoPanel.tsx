import type { ReactNode } from 'react';
import type { Sev } from '../../../lienzo/tipos';

export interface Diagnostico {
  sev: Sev;
  nombre: string;
  momento: string;
  explicacion: string;
  kpis: Array<{ k: string; n: string; v: string; u?: string }>;
  cadena: Array<{ de: string; rel: string; a: string }>;
  recomendacion: string;
}

const NOMBRE_SEV: Record<Sev, string> = {
  normal: 'Operación normal',
  activo: 'En servicio',
  aviso: 'Requiere atención',
  alarma: 'Alarma de proceso',
  inactivo: 'Sin dato disponible',
  info: 'Informativo',
};

/** Diagnóstico del módulo (reglas deterministas sobre los datos en vivo; sin modelo externo). */
export function DiagnosticoPanel({ diag }: { diag: Diagnostico | null }) {
  if (!diag) return <div className="lz-vacio">Calculando diagnóstico…</div>;
  return (
    <div className="lz-diag">
      <div className={`lz-diag-titulo lz-sev-${diag.sev}`}>
        <span className="lz-punto" />
        <div>
          <div className="lz-diag-nombre">{diag.nombre || NOMBRE_SEV[diag.sev]}</div>
          <div className="lz-diag-sub">{diag.momento}</div>
        </div>
      </div>
      <p className="lz-diag-exp">{diag.explicacion}</p>

      {diag.kpis.length > 0 ? (
        <div className="lz-diag-kpis">
          {diag.kpis.map((kpi) => (
            <div key={kpi.k}>
              <span>{kpi.n}</span>
              <b>{kpi.v}</b>
              <small>{kpi.u}</small>
            </div>
          ))}
        </div>
      ) : null}

      {diag.cadena.length > 0 ? (
        <div className="lz-diag-cadena">
          <div className="lz-lbl">Cadena de relaciones</div>
          <ol>
            {diag.cadena.map((arista, index) => (
              <li key={`${arista.de}-${arista.a}-${index}`}>
                <code>{arista.de}</code> <em>{arista.rel}</em> <code>{arista.a}</code>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      <div className="lz-diag-rec">
        <span className="lz-lbl">Recomendación</span>
        {diag.recomendacion}
      </div>
    </div>
  );
}

/** Envoltorio de panel flotante (mismo esqueleto que PanelNode de la tesis). */
export function LienzoPanelBox({
  titulo,
  sub,
  modo,
  children,
}: {
  titulo: string;
  sub?: string;
  modo?: 'vivo' | 'historico';
  children: ReactNode;
}) {
  return (
    <>
      <div className="lz-panel-head">
        <b>{titulo}</b>
        {sub ? <small>{sub}</small> : null}
        {modo ? <span className={`lz-chip-modo ${modo}`}>{modo === 'vivo' ? 'EN VIVO' : 'HISTÓRICO'}</span> : null}
      </div>
      <div className="lz-panel-cuerpo">{children}</div>
    </>
  );
}
