import { useMemo, useState } from 'react';
import { useEstado } from '../ctx';
import { fmtHora, fmtNum } from '../api';

export default function UnsPanel() {
  const { equipo, valores, momento, grafo } = useEstado();
  const BASE = `${equipo?.uns_base ?? ''}/funcional`;
  const [abiertas, setAbiertas] = useState<Record<string, boolean>>({ caudal: true, nivel: true, actuadores: true, bomba: true, estado: true, pid: false });
  const grupos = useMemo(() => {
    const g: Record<string, [string, string][]> = {};
    Object.keys(valores).sort().forEach((v) => {
      const [cab, ...resto] = v.split('/');
      (g[cab] ??= []).push([v, resto.join('/')]);
    });
    return g;
  }, [valores]);
  const nodoDe = useMemo(() => {
    const m: Record<string, string> = {};
    Object.entries(grafo?.nodos ?? {}).forEach(([id, n]) => n.variables.forEach((v) => { m[v] ??= id; }));
    return m;
  }, [grafo]);
  return (
    <div className="uns nowheel">
      <div className="uns-base" title={BASE}>{BASE.replace('/funcional', '')}<b>/funcional</b></div>
      {Object.entries(grupos).map(([cab, hijos]) => (
        <div key={cab} className="uns-grupo">
          <button className="uns-cab" onClick={() => setAbiertas((a) => ({ ...a, [cab]: !a[cab] }))}>
            <span className={`chev ${abiertas[cab] ? 'abierto' : ''}`}>▸</span>{cab}<small>{hijos.length}</small>
          </button>
          {abiertas[cab] && hijos.map(([v, hoja]) => {
            const x = valores[v];
            return (
              <div key={v} className="uns-hoja" title={nodoDe[v] ? `nodo del grafo: ${nodoDe[v]}` : 'sin nodo en el grafo'}>
                <span className="uns-nombre">{hoja}</span>
                <span className="uns-val">{typeof x?.valor === 'boolean' || x?.unidad == null && (x?.valor === 0 || x?.valor === 1)
                  ? (Number(x?.valor) ? 'ON' : 'OFF') : fmtNum(x?.valor, 2)}<small>{x?.unidad ?? ''}</small></span>
                <span className="uns-t">{fmtHora(x?.t)}</span>
              </div>
            );
          })}
        </div>
      ))}
      {Object.keys(grupos).length === 0 && <div className="vacio">{momento ? 'Sin datos en ese momento' : 'Esperando datos del UNS…'}</div>}
    </div>
  );
}
