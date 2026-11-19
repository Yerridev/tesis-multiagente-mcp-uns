import { useState } from 'react';
import type { NodoGrafo, TipoNodo } from './types';

const RELS = ['alimenta', 'acciona', 'impulsa', 'restringe', 'mide', 'lee', 'controla', 'controla_en_local',
  'habilita', 'fija_setpoint', 'ejecuta', 'protege'];
const TIPOS: TipoNodo[] = ['equipo', 'sensor', 'actuador', 'control', 'mando', 'proteccion', 'proceso'];

export function ModalRelacion({ de, a, rel, nota, nombres, onGuardar, onBorrar, onCerrar }: {
  de: string; a: string; rel?: string; nota?: string; nombres: Record<string, string>;
  onGuardar: (rel: string, nota: string) => void; onBorrar?: () => void; onCerrar: () => void;
}) {
  const [r, setR] = useState(rel ?? 'controla');
  const [n, setN] = useState(nota ?? '');
  const valida = /^[a-z0-9_]{1,40}$/.test(r);
  return (
    <div className="modal-fondo" onClick={onCerrar}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={(e) => { e.preventDefault(); if (valida) onGuardar(r, n.trim()); }}>
        <h3>{rel ? 'Editar relación' : 'Nueva relación'}</h3>
        <p className="modal-frase"><b>{nombres[de] ?? de}</b> <span>→</span> <b>{nombres[a] ?? a}</b></p>
        <label>Tipo de relación
          <input list="rels" value={r} onChange={(e) => setR(e.target.value.toLowerCase().replace(/\s+/g, '_'))} autoFocus />
          <datalist id="rels">{RELS.map((x) => <option key={x} value={x} />)}</datalist>
        </label>
        {!valida && <small className="err">Usa minúsculas, dígitos y _ (máx. 40)</small>}
        <label>Nota (opcional)
          <textarea rows={2} value={n} onChange={(e) => setN(e.target.value)} placeholder="Ej.: solo en modo REMOTO" />
        </label>
        <div className="modal-acc">
          {onBorrar && <button type="button" className="peligro" onClick={onBorrar}>Eliminar relación</button>}
          <span />
          <button type="button" onClick={onCerrar}>Cancelar</button>
          <button type="submit" className="primario" disabled={!valida}>Aplicar</button>
        </div>
      </form>
    </div>
  );
}

export function ModalNodo({ existentes, variables, inicial, idInicial, onGuardar, onBorrar, onCerrar }: {
  existentes: string[]; variables: string[]; inicial?: NodoGrafo; idInicial?: string;
  onGuardar: (id: string, n: NodoGrafo) => void; onBorrar?: () => void; onCerrar: () => void;
}) {
  const [id, setId] = useState(idInicial ?? '');
  const [nombre, setNombre] = useState(inicial?.nombre ?? '');
  const [tipo, setTipo] = useState<TipoNodo>(inicial?.tipo ?? 'equipo');
  const [vars, setVars] = useState<string[]>(inicial?.variables ?? []);
  const idOk = /^[a-z0-9_]{1,40}$/.test(id) && (idInicial === id || !existentes.includes(id));
  return (
    <div className="modal-fondo" onClick={onCerrar}>
      <form className="modal ancho" onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); if (idOk && nombre.trim()) onGuardar(id, { tipo, nombre: nombre.trim(), variables: vars }); }}>
        <h3>{idInicial ? 'Editar nodo' : 'Nuevo nodo del grafo'}</h3>
        <div className="modal-fila">
          <label>Id<input value={id} disabled={Boolean(idInicial)} onChange={(e) => setId(e.target.value.toLowerCase().replace(/\s+/g, '_'))} placeholder="filtro_succion" autoFocus /></label>
          <label>Tipo<select value={tipo} onChange={(e) => setTipo(e.target.value as TipoNodo)}>{TIPOS.map((t) => <option key={t}>{t}</option>)}</select></label>
        </div>
        {!idOk && id && <small className="err">Id no válido o repetido</small>}
        <label>Nombre<input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Filtro de succión de la bomba" /></label>
        <fieldset>
          <legend>Variables del UNS que lo describen</legend>
          <div className="modal-vars">
            {variables.map((v) => (
              <label key={v} className="chk">
                <input type="checkbox" checked={vars.includes(v)} onChange={(e) => setVars(e.target.checked ? [...vars, v] : vars.filter((x) => x !== v))} />
                <code>{v}</code>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="modal-acc">
          {onBorrar && <button type="button" className="peligro" onClick={onBorrar}>Eliminar nodo</button>}
          <span />
          <button type="button" onClick={onCerrar}>Cancelar</button>
          <button type="submit" className="primario" disabled={!idOk || !nombre.trim()}>Aplicar</button>
        </div>
      </form>
    </div>
  );
}
