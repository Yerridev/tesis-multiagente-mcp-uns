import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';
import { DiagnosticoPanel } from '../components/lienzo/panels/DiagnosticoPanel';
import { TendenciaPanel } from '../components/lienzo/panels/TendenciaPanel';
import { OrigenPanel } from '../components/lienzo/panels/OrigenPanel';
import { AgentePanel } from '../components/lienzo/panels/AgentePanel';
import { usePaneles, type TipoPanel } from './paneles';

/**
 * Nodo `panel` del lienzo: los 4 paneles viven DENTRO de ReactFlow
 * (idéntico a PanelNode.tsx de la tesis). El arrastre se agarra por la
 * cabecera (dragHandle .lz-panel-head) y el cuerpo es `nodrag nowheel`
 * para que el scroll interno no mueva el lienzo ni lo haga zoom.
 */
function PanelNode({ data }: NodeProps) {
  const { kind } = data as { kind: TipoPanel };
  const { diag, equipo, momento, chip } = usePaneles();

  const TITULOS: Record<TipoPanel, [string, string]> = {
    diagnostico: ['Diagnóstico', `${equipo.diagnosticoRef} · knowledge graph`],
    agente: ['Agente de IA', 'MCP de todos los equipos'],
    tendencia: ['Tendencia', 'búfer de historial del backend'],
    uns: ['Unified Namespace', 'variables que alimentan el lienzo'],
  };
  const [titulo, sub] = TITULOS[kind];

  return (
    <div className={`lz-panel lz-panel-${kind}`}>
      <div className="lz-panel-head">
        <span className="agarre" aria-hidden="true">
          ⋮⋮
        </span>
        <b>{titulo}</b>
        <small>{sub}</small>
        {kind !== 'agente' ? (
          <span className={`lz-chip-modo ${chip}`}>{chip === 'vivo' ? 'EN VIVO' : 'HISTÓRICO'}</span>
        ) : null}
      </div>
      <div className="lz-panel-cuerpo nodrag nowheel">
        {kind === 'diagnostico' ? <DiagnosticoPanel diag={diag} /> : null}
        {kind === 'agente' ? <AgentePanel /> : null}
        {kind === 'tendencia' ? (
          <TendenciaPanel ids={[equipo.id]} unit={equipo.principal.unidad} momento={momento} />
        ) : null}
        {kind === 'uns' ? <OrigenPanel momento={momento} solo={equipo.id} /> : null}
      </div>
    </div>
  );
}

export default memo(PanelNode);
