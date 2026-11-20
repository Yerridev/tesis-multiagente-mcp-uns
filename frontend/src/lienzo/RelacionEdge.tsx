import { memo } from 'react';
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react';
import { useEstado } from './ctx';

/** Relaciones que la tesis dibuja como flujo de proceso (línea sólida). */
const FLUJO = new Set(['alimenta', 'impulsa', 'descarga_en']);

/** Arista portada de RelacionEdge.tsx de la tesis (con nuestros datos en vivo). */
function RelacionEdge(props: EdgeProps) {
  const { id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected } = props;
  const dato = (data ?? {}) as { rel: string; nota?: string };
  const rel = dato.rel;
  const nota = dato.nota;
  const { resalte, flujo, congelado } = useEstado();

  const [path, lx, ly] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 14,
    offset: 22,
  });

  const enCadena = resalte.aristas.has(`${source}|${target}`);

  /* partículas cuando el proceso está en marcha con datos reales */
  const intensidad = flujo.intensidad;
  const fluye = FLUJO.has(rel) && rel !== 'descarga_en' && flujo.activo && intensidad > 0.5;
  const dur = Math.max(1.1, Math.min(7, 66 / Math.max(intensidad, 1)));
  const n = fluye ? Math.max(2, Math.round(intensidad / 10)) : 0;

  const cls = ['rel', FLUJO.has(rel) ? 'rel-flujo' : '', enCadena ? `en-cadena fuente-${resalte.fuente ?? 'diagnostico'}` : '', congelado ? 'rel-congelado' : '', selected ? 'sel' : '']
    .filter(Boolean)
    .join(' ');

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        className={cls}
        markerEnd={`url(#flecha-${enCadena ? 'cadena' : 'normal'})`}
        interactionWidth={18}
      />
      {fluye ? (
        <g className="particulas">
          {Array.from({ length: n }, (_, i) => (
            <circle key={i} r={2.6}>
              <animateMotion dur={`${dur}s`} repeatCount="indefinite" begin={`${(-i * dur) / n}s`} path={path} />
            </circle>
          ))}
        </g>
      ) : null}
      <EdgeLabelRenderer>
        <div className="rel-etq" style={{ transform: `translate(-50%, -50%) translate(${lx}px, ${ly}px)` }} title={nota ?? ''}>
          {rel.replace(/_/g, ' ')}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export default memo(RelacionEdge);
