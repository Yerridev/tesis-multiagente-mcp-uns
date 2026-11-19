import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { useEstado, valorNum } from '../ctx';
import { Icono } from '../icons';
import { lectura } from './lecturas';
import type { NodoGrafo } from '../types';

const TIPO_TXT: Record<string, string> = {
  equipo: 'Equipo', sensor: 'Sensor', actuador: 'Actuador', control: 'Control', mando: 'Mando',
  proteccion: 'Protección', proceso: 'Proceso',
};

const LADOS: [Position, string][] = [
  [Position.Top, 'top'], [Position.Right, 'right'], [Position.Bottom, 'bottom'], [Position.Left, 'left'],
];

function EquipoNode({ id, data, selected }: NodeProps) {
  const nodo = (data as { nodo: NodoGrafo }).nodo;
  const { equipo, valores, enlace, diag, resalte, agenteTocando, editando } = useEstado();
  const L = lectura(equipo?.id, id, nodo.variables, valores, enlace, diag);
  const varPct = (valorNum(valores, equipo?.velocidad?.variable) ?? 0) * (equipo?.velocidad?.factor_pct ?? 1);
  const marcha = (valorNum(valores, equipo?.marcha) ?? 0) >= 0.5;
  const enCadena = resalte.nodos.has(id);
  const tocado = agenteTocando.has(id);
  const cls = ['eq', `tipo-${nodo.tipo}`, enCadena ? `en-cadena fuente-${resalte.fuente}` : '', tocado ? 'tocado' : '',
    selected ? 'sel' : '', L.estado ? `sev-${L.estado.sev}` : ''].join(' ');
  return (
    <div className={cls}>
      {LADOS.map(([pos, k]) => (
        <span key={k}>
          <Handle type="target" position={pos} id={`t-${k}`} className={editando ? 'h-edit' : 'h-oculto'} />
          <Handle type="source" position={pos} id={`s-${k}`} className={editando ? 'h-edit' : 'h-oculto'} />
        </span>
      ))}
      <div className="eq-head">
        <div className="eq-ico">
          <Icono id={id} tipo={nodo.tipo} activo={id === 'bomba' ? marcha : id === 'selector' ? (valorNum(valores, 'estado/selector_remoto') ?? 0) >= 0.5 : undefined}
            giro={marcha ? Math.max(0.35, 2.4 - (2 * varPct) / 100) : undefined} />
        </div>
        <div className="eq-tit">
          <div className="eq-tipo">{TIPO_TXT[nodo.tipo] ?? nodo.tipo}</div>
          <div className="eq-nombre" title={nodo.nombre}>{nodo.nombre}</div>
        </div>
      </div>
      {L.estado && <div className={`eq-estado sev-${L.estado.sev}`}>{L.estado.texto}</div>}
      {L.principal && (
        <div className="eq-principal">
          <span className="num">{L.principal.valor}</span>
          <span className="uni">{L.principal.unidad}</span>
        </div>
      )}
      {L.barra && (
        <div className="eq-barra" aria-label={L.barra.etiqueta}>
          <div className={`relleno sev-${L.barra.sev}`} style={{ width: `${L.barra.pct}%` }} />
          <span>{L.barra.etiqueta}</span>
        </div>
      )}
      {L.filas.length > 0 && (
        <dl className="eq-filas">
          {L.filas.map((f) => (
            <div key={f.k}>
              <dt>{f.k}</dt>
              <dd>{f.v}{f.u ? <small> {f.u}</small> : null}</dd>
            </div>
          ))}
        </dl>
      )}
      {tocado && <div className="eq-agente">consultado por el agente</div>}
    </div>
  );
}

export default memo(EquipoNode);
