import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import DiagnosticoPanel from '../panels/DiagnosticoPanel';
import AgentePanel from '../panels/AgentePanel';
import TendenciaPanel from '../panels/TendenciaPanel';
import UnsPanel from '../panels/UnsPanel';
import { useEstado } from '../ctx';

const TITULO: Record<string, [string, string]> = {
  diagnostico: ['Diagnóstico del lazo', 'diagnosticar_lazo · knowledge graph'],
  agente: ['Agente de IA', 'Claude + MCP'],
  tendencia: ['Tendencia', 'TimescaleDB'],
  uns: ['Unified Namespace', 'MQTT en vivo'],
};

function PanelNode({ data }: NodeProps) {
  const d = data as { kind: string; agenteHabilitado?: boolean; modelo?: string };
  const { momento } = useEstado();
  const [t, sub] = TITULO[d.kind] ?? [d.kind, ''];
  return (
    <div className={`panel panel-${d.kind}`}>
      <div className="panel-head">
        <span className="agarre" aria-hidden="true">⋮⋮</span>
        <b>{t}</b>
        <small>{sub}</small>
        {d.kind !== 'agente' && <span className={`chip-modo ${momento ? 'hist' : 'vivo'}`}>{momento ? 'HISTÓRICO' : 'EN VIVO'}</span>}
      </div>
      <div className="panel-cuerpo nodrag">
        {d.kind === 'diagnostico' && <DiagnosticoPanel />}
        {d.kind === 'agente' && <AgentePanel habilitado={Boolean(d.agenteHabilitado)} modelo={d.modelo ?? ''} />}
        {d.kind === 'tendencia' && <TendenciaPanel />}
        {d.kind === 'uns' && <UnsPanel />}
      </div>
    </div>
  );
}

export default memo(PanelNode);
