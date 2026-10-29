import { useEffect, useRef, useState } from 'react';
import { conversar } from '../api';
import { useAcciones } from '../acciones';
import { IcoEnviar } from '../icons';
import type { Arista } from '../types';

interface Paso {
  id: string;
  nombre: string; // nombre de la herramienta sin prefijo
  alias: string;  // equipo al que consulta (caudal, nivel...)
  equipo?: string;
  entrada: Record<string, unknown>;
  ms?: number;
  error?: boolean;
  resumen?: string;
}

interface Turno {
  role: 'user' | 'assistant';
  content: string;
  pasos?: Paso[];
  error?: string;
}

const GENERALES = [
  '¿Cómo están todos los equipos del laboratorio ahora?',
  '¿Qué equipos tienen alguna alarma o advertencia?',
  '¿Qué equipos están en marcha y en qué modo?',
];

function resumen(nombre: string, d: Record<string, unknown> | null): string {
  if (!d) return '';
  if (typeof d.diagnostico === 'string') return d.diagnostico.replace(/_/g, ' ').toLowerCase();
  if (typeof d.evaluacion === 'string') return String(d.evaluacion).replace(/_/g, ' ').toLowerCase();
  if (Array.isArray(d.lecturas)) return `${d.lecturas.length} lectura(s)`;
  if (typeof d.muestras === 'number') return `${d.muestras} muestras`;
  if (nombre === 'obtener_estado_plc' && typeof d.modo === 'string') return `modo ${String(d.modo).toLowerCase()}`;
  return 'ok';
}

/** Chat con el agente. 'equipo' = equipo visible (null en la vista general: el agente coordina todos los equipos).
 *  Las herramientas llegan como "<alias>__<herramienta>"; solo se resalta en el lienzo lo del equipo visible. */
export default function AgentePanel({ habilitado, modelo, equipo, sugerencias }: {
  habilitado: boolean; modelo: string; equipo: string | null; sugerencias?: string[];
}) {
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [texto, setTexto] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const fin = useRef<HTMLDivElement>(null);
  const { agenteToca, agenteCadena, nodosDeVariables } = useAcciones();
  const lista = sugerencias && sugerencias.length ? sugerencias : GENERALES;

  useEffect(() => {
    fin.current?.scrollIntoView({ block: 'end' }); // en Chrome reciente devuelve una promesa: no retornarla
  }, [turnos]);

  async function enviar(pregunta: string) {
    const p = pregunta.trim();
    if (!p || ocupado) return;
    const previos = turnos.filter((t) => !t.error).map(({ role, content }) => ({ role, content }));
    const historial = [...previos, { role: 'user' as const, content: p }];
    setTurnos((t) => [...t, { role: 'user', content: p }, { role: 'assistant', content: '', pasos: [] }]);
    setTexto('');
    setOcupado(true);
    const actualizar = (f: (t: Turno) => Turno) =>
      setTurnos((ts) => ts.map((t, i) => (i === ts.length - 1 ? f(t) : t)));
    await conversar(historial, equipo, (ev) => {
      switch (ev.tipo) {
        case 'texto':
          actualizar((t) => ({ ...t, content: t.content + String(ev.delta ?? '') }));
          break;
        case 'herramienta': {
          const entrada = (ev.entrada ?? {}) as Record<string, unknown>;
          const [alias, nombre] = String(ev.nombre).includes('__') ? String(ev.nombre).split('__', 2) : ['', String(ev.nombre)];
          actualizar((t) => ({ ...t, pasos: [...(t.pasos ?? []), { id: String(ev.id), nombre, alias, equipo: ev.equipo as string, entrada }] }));
          if (equipo && ev.equipo === equipo) {
            const vars = [
              ...(Array.isArray(entrada.variables) ? (entrada.variables as string[]) : []),
              ...(typeof entrada.variable === 'string' ? [entrada.variable] : []),
            ];
            const nodos = nodosDeVariables(vars);
            if (typeof entrada.entidad === 'string') nodos.push(entrada.entidad);
            if (nombre === 'obtener_estado_plc') nodos.push('plc', 'bomba', 'selector');
            if (nodos.length) agenteToca(nodos);
          }
          break;
        }
        case 'resultado': {
          const datos = (ev.datos ?? null) as Record<string, unknown> | null;
          actualizar((t) => ({
            ...t,
            pasos: (t.pasos ?? []).map((x) => x.id === ev.id
              ? { ...x, ms: Number(ev.ms), error: Boolean(ev.error), resumen: resumen(x.nombre, datos) } : x),
          }));
          if (equipo && ev.equipo === equipo && datos && Array.isArray(datos.aristas_causales)) {
            const ar = [...(datos.aristas_causales as Arista[])];
            ((datos.hallazgos_secundarios as { aristas?: Arista[] }[]) ?? []).forEach((h) => ar.push(...(h.aristas ?? [])));
            if (ar.length) agenteCadena(ar);
          }
          break;
        }
        case 'error':
          actualizar((t) => ({ ...t, error: String(ev.detalle) }));
          break;
      }
    });
    setOcupado(false);
  }

  return (
    <div className="agente">
      <div className="agente-chat nowheel">
        {turnos.length === 0 && (
          <div className="agente-vacio">
            <p>{equipo
              ? 'Pregunta sobre este módulo (o sobre otro: el agente tiene acceso a todos). Marca en el lienzo lo que consulta.'
              : 'Vista general: el agente consulta a cada equipo con sus propias herramientas MCP y compara los resultados.'}</p>
            <div className="sugerencias">
              {lista.map((s) => (
                <button key={s} disabled={!habilitado || ocupado} onClick={() => enviar(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {turnos.map((t, i) => (
          <div key={i} className={`turno ${t.role}`}>
            {t.pasos && t.pasos.length > 0 && (
              <div className="pasos">
                {t.pasos.map((p) => (
                  <span key={p.id} className={`paso ${p.ms === undefined ? 'corriendo' : ''} ${p.error ? 'err' : ''}`}
                    title={JSON.stringify(p.entrada)}>
                    {p.alias && <b className="paso-eq">{p.alias}</b>}
                    <code>{p.nombre}</code>
                    {p.resumen && <em>{p.resumen}</em>}
                    {p.ms !== undefined && <small>{p.ms} ms</small>}
                  </span>
                ))}
              </div>
            )}
            {t.content && <div className="burbuja">{t.content}</div>}
            {t.error && <div className="burbuja error">No se pudo consultar al agente: {t.error}</div>}
            {t.role === 'assistant' && !t.content && !t.error && ocupado && i === turnos.length - 1 && (
              <div className="pensando"><span /><span /><span /></div>
            )}
          </div>
        ))}
        <div ref={fin} />
      </div>
      <form className="agente-entrada" onSubmit={(e) => { e.preventDefault(); enviar(texto); }}>
        <textarea rows={2} value={texto} disabled={!habilitado}
          placeholder={habilitado ? 'Pregunta al agente… (Enter para enviar)' : 'Configura la clave del proveedor (OPENROUTER_API_KEY, GEMINI_API_KEY o ANTHROPIC_API_KEY) en el .env'}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar(texto); } }} />
        <button type="submit" disabled={!habilitado || ocupado || !texto.trim()} aria-label="Enviar"><IcoEnviar /></button>
      </form>
      <div className="agente-pie">{modelo} · MCP de todos los equipos · solo lectura</div>
    </div>
  );
}
