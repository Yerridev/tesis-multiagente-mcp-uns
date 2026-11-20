import { memo, useEffect, useRef, useState } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { useEstado } from './ctx';
import type { MetaNodo } from './tipos';

/** Lados de conexión (idéntico a EquipoNode.tsx de la tesis). */
const LADOS: [Position, string][] = [
  [Position.Top, 'top'],
  [Position.Right, 'right'],
  [Position.Bottom, 'bottom'],
  [Position.Left, 'left'],
];

/** Barra de porcentaje: texto centrado, relleno animado, color según el valor y flecha de tendencia. */
function Barra({ pct, sev, etiqueta }: { pct: number; sev: string; etiqueta: string }) {
  const v = Math.max(0, Math.min(100, pct));
  const previo = useRef<number | null>(null);
  const [tendencia, setTendencia] = useState<'sube' | 'baja' | null>(null);
  useEffect(() => {
    const antes = previo.current;
    previo.current = v;
    if (antes == null || Math.abs(v - antes) < 0.2) return;
    setTendencia(v > antes ? 'sube' : 'baja');
    const t = window.setTimeout(() => setTendencia(null), 2500);
    return () => window.clearTimeout(t);
  }, [v]);
  /* normal: azul que se oscurece al aumentar; aviso/alarma conservan su color */
  const fondo = sev === 'aviso' || sev === 'alarma' ? undefined : `hsl(207, 75%, ${86 - v * 0.36}%)`;
  return (
    <div className="eq-barra" aria-label={etiqueta}>
      <div className={`relleno sev-${sev}`} style={{ width: `${v}%`, background: fondo }} />
      <span className="eq-barra-txt">
        {tendencia === 'sube' ? <b className="eq-tend sube">▲</b> : tendencia === 'baja' ? <b className="eq-tend baja">▼</b> : null}
        {etiqueta}
      </span>
    </div>
  );
}

/** Nodo de equipo portado de la tesis (EquipoNode.tsx): metadatos en data.meta y valores por contexto. */
function EquipoNode({ data, selected }: NodeProps) {
  const meta = (data as { meta: MetaNodo }).meta;
  const { resalte, agenteTocando, editando, lecturas } = useEstado();
  const lec = lecturas[meta.id] ?? { filas: [] };

  const enCadena = resalte.nodos.has(meta.id);
  const tocado = agenteTocando.has(meta.id);
  const sev = lec.estado?.sev ?? 'normal';

  const cls = [
    'eq',
    enCadena ? `en-cadena fuente-${resalte.fuente ?? 'diagnostico'}` : '',
    tocado ? 'tocado' : '',
    selected ? 'sel' : '',
    lec.estado ? `sev-${sev}` : '',
    lec.congelado ? 'congelado' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cls}>
      {LADOS.map(([pos, k]) => (
        <span key={k}>
          <Handle type="target" position={pos} id={`t-${k}`} className="h-oculto" />
          <Handle type="source" position={pos} id={`s-${k}`} className="h-oculto" />
        </span>
      ))}

      <div className="eq-head">
        <div className="eq-ico" aria-hidden="true">
          {meta.icono}
        </div>
        <div className="eq-tit">
          <div className="eq-tipo">{meta.tipo}</div>
          <div className="eq-nombre" title={meta.nombre}>
            {meta.nombre}
          </div>
        </div>
      </div>

      {lec.estado ? <div className={`eq-estado sev-${lec.estado.sev}`}>{lec.estado.texto}</div> : null}

      {lec.principal ? (
        <div className="eq-principal">
          <span className="num">{lec.principal.valor}</span>
          <span className="uni">{lec.principal.unidad}</span>
        </div>
      ) : null}

      {lec.barra ? (
        <Barra pct={lec.barra.pct} sev={lec.barra.sev} etiqueta={lec.barra.etiqueta} />
      ) : null}

      {lec.filas.length > 0 ? (
        <dl className="eq-filas">
          {lec.filas.map((f, i) => (
            <div key={`${f.k}-${i}`}>
              <dt>{f.k}</dt>
              <dd className={/sin datos|^—$|^n\/d/i.test(f.v) ? 'nodata' : undefined}>
                {f.v}
                {f.u ? <small> {f.u}</small> : null}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {tocado ? <div className="eq-agente">consultado por el agente</div> : null}
      {editando ? null : null}
    </div>
  );
}

export default memo(EquipoNode);
