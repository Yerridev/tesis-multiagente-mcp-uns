import { useEstado, severidad } from '../ctx';
import { fmtHora, fmtNum } from '../api';

const NOMBRE: Record<string, string> = {
  REGULANDO: 'Regulando',
  SATURADO_FUERA_DE_CAPACIDAD: 'Saturado: fuera de capacidad',
  SATURADO_EN_MINIMO: 'Saturado en el mínimo',
  BOMBA_DETENIDA: 'Bomba detenida',
  TRANSITORIO: 'Transitorio',
  CONTROL_MANUAL_LOCAL: 'Control manual (LOCAL)',
  PID_SIN_HABILITAR: 'PID sin habilitar',
  DESVIACION_SIN_SATURAR: 'Desviación sin saturar',
  SIN_DATOS: 'Sin datos en vivo',
};

export default function DiagnosticoPanel() {
  const { diag, momento } = useEstado();
  if (!diag) return <div className="vacio">Calculando diagnóstico…</div>;
  const sev = severidad(diag.diagnostico);
  const e = diag.evidencia;
  return (
    <div className="diag">
      <div className={`diag-titulo sev-${sev}`}>
        <span className="punto" />
        <div>
          <div className="diag-nombre">{NOMBRE[diag.diagnostico] ?? diag.diagnostico}</div>
          <div className="diag-sub">{momento ? 'Reproducción' : 'En vivo'} · {fmtHora(diag.momento_evaluado)} · ventana 30 s</div>
        </div>
      </div>
      <p className="diag-exp">{diag.explicacion}</p>
      <div className="diag-kpis">
        <div><span>Setpoint</span><b>{fmtNum(e.setpoint_lpm)}</b><small>L/min</small></div>
        <div><span>Caudal</span><b>{fmtNum(e.caudal_promedio_30s_lpm)}</b><small>L/min</small></div>
        <div><span>Error</span><b>{fmtNum(e.error_lpm, 2)}</b><small>L/min</small></div>
        <div><span>Variador</span><b>{fmtNum(e.variador_pct, 0)}</b><small>%</small></div>
      </div>
      {diag.cadena_causal.length > 0 && (
        <div className="diag-cadena">
          <div className="lbl">Cadena causal (knowledge graph)</div>
          <ol>
            {(diag.aristas_causales ?? []).map((a, i) => (
              <li key={i}><code>{a.de}</code> <em>{a.rel.replace(/_/g, ' ')}</em> <code>{a.a}</code></li>
            ))}
          </ol>
        </div>
      )}
      {diag.hallazgos_secundarios.map((h) => (
        <div key={h.hallazgo} className={`diag-hallazgo ${h.hallazgo === 'PARADA_TRAS_SATURACION' || h.hallazgo === 'NIVEL_BAJO' || h.hallazgo === 'SENSORES_INCOHERENTES' ? 'sev-alarma' : 'sev-aviso'}`}>
          <b>{h.hallazgo.replace(/_/g, ' ').toLowerCase()}</b>
          <span>{h.detalle}</span>
        </div>
      ))}
      <div className="diag-rec"><span className="lbl">Recomendación</span>{diag.recomendacion}</div>
    </div>
  );
}
