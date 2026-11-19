import { memo } from 'react';
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react';
import { useEstado, valorNum } from '../ctx';

const FLUJO = new Set(['alimenta', 'impulsa', 'descarga_en']);

function RelacionEdge(props: EdgeProps) {
  const { id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected } = props;
  const rel = (data as { rel: string; nota?: string }).rel;
  const nota = (data as { nota?: string }).nota;
  const { equipo, valores, resalte, editando } = useEstado();
  const [path, lx, ly] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 14, offset: 22 });
  const enCadena = resalte.aristas.has(`${source}|${target}`);
  // intensidad del flujo segun el equipo (caudal real en caudal; frecuencia de la bomba como proxy en nivel)
  const caudal = (valorNum(valores, equipo?.flujo?.variable) ?? 0) * (equipo?.flujo?.factor ?? 1);
  const marcha = (valorNum(valores, equipo?.marcha) ?? 0) >= 0.5;
  const fluye = FLUJO.has(rel) && rel !== 'descarga_en' && marcha && caudal > 0.5;
  // 60 L/min -> 1,1 s por recorrido; 5 L/min -> ~6 s
  const dur = Math.max(1.1, Math.min(7, 66 / Math.max(caudal, 1)));
  const n = fluye ? Math.max(2, Math.round(caudal / 10)) : 0;
  const cls = ['rel', FLUJO.has(rel) ? 'rel-flujo' : '', enCadena ? `en-cadena fuente-${resalte.fuente}` : '',
    selected ? 'sel' : ''].join(' ');
  return (
    <>
      <BaseEdge id={id} path={path} className={cls} markerEnd={`url(#flecha-${enCadena ? 'cadena' : 'normal'})`}
        interactionWidth={18} />
      {fluye && (
        <g className="particulas">
          {Array.from({ length: n }, (_, i) => (
            <circle key={i} r={2.6}>
              <animateMotion dur={`${dur}s`} repeatCount="indefinite" begin={`${(-i * dur) / n}s`} path={path} />
            </circle>
          ))}
        </g>
      )}
      <EdgeLabelRenderer>
        <div className={`rel-etq ${enCadena ? 'en-cadena' : ''} ${editando ? 'editable' : ''}`}
          style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)` }} title={nota ?? ''}>
          {rel.replace(/_/g, ' ')}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export default memo(RelacionEdge);
