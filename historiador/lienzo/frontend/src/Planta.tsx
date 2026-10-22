import { fmtHora, fmtNum } from './api';
import { NOMBRE_DIAG, severidad } from './ctx';
import AgentePanel from './panels/AgentePanel';
import { IcoCandado, IcoLuna, IcoSol } from './icons';
import { Pill } from './VistaEquipo';
import type { EquipoCfg, Organizacion, ResumenEquipo, Salud } from './types';

export type SevEquipo = 'normal' | 'aviso' | 'alarma' | 'info' | 'sin_datos';

/** Estado resumido de un equipo para tarjetas y navegacion (ISA-101: gris lo normal, color lo anormal). */
export function sevEquipo(r?: ResumenEquipo): SevEquipo {
  if (!r || r.error || !r.enlace) return 'sin_datos';
  if (!r.enlace.datos_en_vivo) return 'sin_datos';
  const s = severidad(r.diagnostico?.diagnostico);
  return s;
}

export const TXT_SEV: Record<SevEquipo, string> = {
  normal: 'Operando', aviso: 'Atención', alarma: 'Alarma', info: 'Informativo', sin_datos: 'Sin datos en vivo',
};

function num(r: ResumenEquipo | undefined, v?: string): number | null {
  if (!r?.valores || !v) return null;
  const x = r.valores[v]?.valor;
  if (x === null || x === undefined) return null;
  return typeof x === 'boolean' ? (x ? 1 : 0) : Number(x);
}

function Spark({ datos, min, max }: { datos: [string, number][]; min?: number; max?: number }) {
  if (datos.length < 2) return <div className="spark vacio-spark">sin tendencia en los últimos 30 min</div>;
  const ys = datos.map((d) => d[1]);
  const lo = min ?? Math.min(...ys);
  const hi = Math.max(max ?? Math.max(...ys), lo + 1e-6);
  const t0 = Date.parse(datos[0][0]);
  const t1 = Date.parse(datos[datos.length - 1][0]);
  const pts = datos.map(([t, v]) => {
    const x = ((Date.parse(t) - t0) / Math.max(1, t1 - t0)) * 100;
    const y = 30 - ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * 28 - 1;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  return (
    <svg className="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts.join(' ')} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Tarjeta({ e, r, onAbrir }: { e: EquipoCfg; r?: ResumenEquipo; onAbrir: () => void }) {
  const sev = sevEquipo(r);
  const p = e.principal;
  const s = e.secundario;
  const vp = num(r, p.variable);
  const vs = num(r, s?.variable);
  const marcha = num(r, e.marcha);
  const remoto = num(r, 'estado/selector_remoto');
  const local = num(r, 'estado/selector_local');
  const modo = remoto === null && local === null ? '—' : (remoto ?? 0) >= 0.5 ? 'REMOTO' : (local ?? 0) >= 0.5 ? 'LOCAL' : 'EN 0';
  const fueraP = vp !== null && ((p.alarma !== undefined && vp >= p.alarma) ? 'alarma' : (p.aviso !== undefined && vp >= p.aviso) ? 'aviso' : '');
  const d = r?.diagnostico;
  return (
    <article className={`tarjeta sev-${sev}`}>
      <header className="tj-cab">
        <div>
          <div className="tj-cod">{e.codigo} · {e.proceso}</div>
          <h2>{e.nombre}</h2>
        </div>
        <span className={`tj-sem sev-${sev}`}><span className="punto" />{TXT_SEV[sev]}</span>
      </header>
      <div className="tj-medida">
        <div className={`tj-principal ${fueraP || ''}`}>
          <span className="num">{fmtNum(vp, p.decimales ?? 1)}</span>
          <span className="uni">{p.unidad}</span>
          <small>{p.nombre}</small>
        </div>
        {s && (
          <div className="tj-sec">
            <span className="num">{fmtNum(vs, s.decimales ?? 1)}</span> <small>{s.unidad} · {s.nombre}</small>
          </div>
        )}
      </div>
      <Spark datos={r?.spark ?? []} min={p.min} max={p.max} />
      <div className="tj-chips">
        <span className={`chip ${modo === 'LOCAL' ? 'aviso' : ''}`}>Modo {modo}</span>
        <span className={`chip ${marcha !== null && marcha >= 0.5 ? 'on' : ''}`}>
          Bomba {marcha === null ? '—' : marcha >= 0.5 ? 'en marcha' : 'detenida'}
        </span>
        <span className="chip">PLC {r?.enlace?.conexion_plc === 'CONECTADO' ? 'conectado' : (r?.enlace?.conexion_plc ?? 'sin dato').toLowerCase()}</span>
      </div>
      <div className={`tj-diag sev-${severidad(d?.diagnostico)}`}>
        <b>{d ? NOMBRE_DIAG[d.diagnostico] ?? d.diagnostico : 'Sin diagnóstico'}</b>
        <span>{r?.error ? r.error : d?.explicacion ?? (r ? '' : 'Consultando…')}</span>
      </div>
      <footer className="tj-pie">
        <span title={e.protocolo}>{e.plc} · {e.ip}</span>
        <button className="primario" onClick={onAbrir}>Abrir lienzo →</button>
      </footer>
    </article>
  );
}

interface Props {
  org: Organizacion;
  equipos: EquipoCfg[];
  resumen: Record<string, ResumenEquipo>;
  consultado: string | null;
  salud: Salud | null;
  tema: 'oscuro' | 'claro';
  setTema: (t: 'oscuro' | 'claro') => void;
  abrir: (id: string) => void;
}

/** Vista general del laboratorio: una tarjeta por equipo registrado + agente coordinador de todos los equipos. */
export default function Planta({ org, equipos, resumen, consultado, salud, tema, setTema, abrir }: Props) {
  const enLinea = equipos.filter((e) => resumen[e.id]?.enlace?.datos_en_vivo).length;
  const atencion = equipos.filter((e) => ['aviso', 'alarma', 'sin_datos'].includes(sevEquipo(resumen[e.id])));
  return (
    <div className="app">
      <header className="barra">
        <div className="marca">
          <div className="logo" aria-hidden="true"><span /><span /><span /></div>
          <div>
            <h1>{org.area ?? 'Laboratorio'} · Vista general</h1>
            <p>{org.campus ?? 'USS'} · aula {org.aula ?? '—'} · UNS <code>{org.uns_raiz ?? ''}</code></p>
          </div>
        </div>
        <div className="estados">
          <Pill ok={salud?.db} txt="Historiador" />
          <Pill ok={salud?.mqtt} txt="UNS / MQTT" />
          <span className={`pill ${enLinea === equipos.length ? 'ok' : 'mal'}`}><span className="punto" />{enLinea}/{equipos.length} equipos en línea</span>
          <span className="pill ro" title="Ninguna parte del lienzo puede escribir en los PLC"><IcoCandado /> Solo lectura</span>
        </div>
        <div className="acciones">
          <button className="icono" onClick={() => setTema(tema === 'oscuro' ? 'claro' : 'oscuro')} aria-label="Cambiar tema">
            {tema === 'oscuro' ? <IcoSol /> : <IcoLuna />}
          </button>
        </div>
      </header>
      <div className="planta">
        <main className="planta-cuerpo">
          <section aria-labelledby="t-equipos">
            <div className="sec-cab">
              <h2 id="t-equipos">Equipos integrados</h2>
              <small>Actualizado {fmtHora(consultado)} · cada 5 s</small>
            </div>
            <div className="tarjetas">
              {equipos.map((e) => <Tarjeta key={e.id} e={e} r={resumen[e.id]} onAbrir={() => abrir(e.id)} />)}
            </div>
          </section>
          <section aria-labelledby="t-atencion" className="atencion">
            <div className="sec-cab"><h2 id="t-atencion">Requiere atención</h2><small>{atencion.length} equipo(s)</small></div>
            {atencion.length === 0 && <div className="vacio">Todos los equipos operan sin alarmas.</div>}
            {atencion.map((e) => {
              const r = resumen[e.id];
              const sev = sevEquipo(r);
              return (
                <button key={e.id} className={`aten-fila sev-${sev}`} onClick={() => abrir(e.id)}>
                  <span className="punto" />
                  <b>{e.codigo}</b>
                  <span>{sev === 'sin_datos' ? (r?.enlace?.motivos ?? []).join('; ') || 'sin datos en vivo'
                    : `${NOMBRE_DIAG[r?.diagnostico?.diagnostico ?? ''] ?? r?.diagnostico?.diagnostico}: ${r?.diagnostico?.recomendacion ?? ''}`}</span>
                </button>
              );
            })}
          </section>
        </main>
        <aside className="planta-agente panel">
          <div className="panel-head" style={{ cursor: 'default' }}>
            <b>Agente coordinador</b>
            <small>consulta a cada equipo con su servidor MCP</small>
          </div>
          <div className="panel-cuerpo">
            <AgentePanel habilitado={Boolean(salud?.agente)} modelo={salud?.modelo ?? ''} equipo={null} />
          </div>
        </aside>
      </div>
    </div>
  );
}
