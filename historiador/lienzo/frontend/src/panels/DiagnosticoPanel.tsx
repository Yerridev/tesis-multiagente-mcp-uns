import { useEstado, severidad, NOMBRE_DIAG } from '../ctx';
import { fmtHora, fmtNum } from '../api';

const ALARMAS = new Set(['PARADA_TRAS_SATURACION', 'NIVEL_BAJO', 'SENSORES_INCOHERENTES', 'SENSOR_SATURADO', 'T1_BAJO_CON_BOMBA']);

export default function DiagnosticoPanel() {
  const { equipo, diag, momento } = useEstado();
  if (!diag) return <div className="vacio">Calculando diagnóstico…</div>;
  const sev = severidad(diag.diagnostico);
  const e = (diag.evidencia ?? {}) as Record<string, unknown>;
  const kpis = equipo?.kpis ?? [];
  return (
    <div className="diag">
      <div className={`diag-titulo sev-${sev}`}>
        <span className="punto" />
        <div>
          <div className="diag-nombre">{NOMBRE_DIAG[diag.diagnostico] ?? diag.diagnostico}</div>
          <div className="diag-sub">{momento ? 'Reproducción' : 'En vivo'} · {fmtHora(diag.momento_evaluado)} · ventana 30 s</div>
        </div>
      </div>
      <p className="diag-exp">{diag.explicacion}</p>
      {kpis.length > 0 && (
        <div className="diag-kpis" style={{ gridTemplateColumns: `repeat(${Math.min(kpis.length, 4)}, 1fr)` }}>
          {kpis.map((k) => (
            <div key={k.k}><span>{k.n}</span><b>{fmtNum(e[k.k], k.d ?? 1)}</b><small>{k.u}</small></div>
          ))}
        </div>
      )}
      {(diag.aristas_causales ?? []).length > 0 && (
        <div className="diag-cadena">
          <div className="lbl">Cadena causal (knowledge graph)</div>
          <ol>
            {(diag.aristas_causales ?? []).map((a, i) => (
              <li key={i}><code>{a.de}</code> <em>{a.rel.replace(/_/g, ' ')}</em> <code>{a.a}</code></li>
            ))}
          </ol>
        </div>
      )}
      {(diag.hallazgos_secundarios ?? []).map((h) => (
        <div key={h.hallazgo} className={`diag-hallazgo ${ALARMAS.has(h.hallazgo) ? 'sev-alarma' : 'sev-aviso'}`}>
          <b>{h.hallazgo.replace(/_/g, ' ').toLowerCase()}</b>
          <span>{h.detalle}</span>
        </div>
      ))}
      <div className="diag-rec"><span className="lbl">Recomendación</span>{diag.recomendacion}</div>
    </div>
  );
}
