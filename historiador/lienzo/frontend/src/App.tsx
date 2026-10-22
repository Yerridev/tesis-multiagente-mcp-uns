import { useCallback, useEffect, useState } from 'react';
import './estilos.css';
import { api } from './api';
import Planta, { sevEquipo, TXT_SEV } from './Planta';
import VistaEquipo from './VistaEquipo';
import type { EquipoCfg, Organizacion, ResumenEquipo, Salud } from './types';

function leerTema(): 'oscuro' | 'claro' {
  try { return (localStorage.getItem('lienzo-tema') as 'oscuro' | 'claro') || 'oscuro'; } catch { return 'oscuro'; }
}
function leerNav(): boolean {
  try { return localStorage.getItem('lienzo-nav') !== 'compacta'; } catch { return true; }
}

/** Ruta en el hash: '#/' = vista general; '#/equipo/<id>' = lienzo de un equipo. */
function rutaActual(): string | null {
  const m = location.hash.match(/^#\/equipo\/([\w-]+)/);
  return m ? m[1] : null;
}

/** Contenedor: navegacion por el arbol del UNS (laboratorio > aula > equipos) + vista general o lienzo del equipo. */
export default function App() {
  const [org, setOrg] = useState<Organizacion>({});
  const [equipos, setEquipos] = useState<EquipoCfg[] | null>(null);
  const [errorReg, setErrorReg] = useState<string | null>(null);
  const [resumen, setResumen] = useState<Record<string, ResumenEquipo>>({});
  const [consultado, setConsultado] = useState<string | null>(null);
  const [salud, setSalud] = useState<Salud | null>(null);
  const [tema, setTema] = useState<'oscuro' | 'claro'>(leerTema);
  const [navAbierta, setNavAbierta] = useState(leerNav);
  const [ruta, setRuta] = useState<string | null>(rutaActual);

  useEffect(() => {
    document.documentElement.dataset.tema = tema;
    try { localStorage.setItem('lienzo-tema', tema); } catch { /* sin almacenamiento */ }
  }, [tema]);
  useEffect(() => {
    try { localStorage.setItem('lienzo-nav', navAbierta ? 'abierta' : 'compacta'); } catch { /* nada */ }
  }, [navAbierta]);

  useEffect(() => {
    const f = () => setRuta(rutaActual());
    window.addEventListener('hashchange', f);
    return () => window.removeEventListener('hashchange', f);
  }, []);

  useEffect(() => {
    api.equipos().then((r) => { setOrg(r.organizacion); setEquipos(r.equipos); })
      .catch((e) => setErrorReg(String((e as Error).message)));
    const cargarSalud = () => api.salud().then(setSalud).catch(() => setSalud(null));
    cargarSalud();
    const idS = window.setInterval(cargarSalud, 15000);
    return () => window.clearInterval(idS);
  }, []);

  // resumen de planta: alimenta las tarjetas y los semaforos del arbol (en el lienzo de un equipo, mas espaciado)
  useEffect(() => {
    let vigente = true;
    const cargar = () => api.planta().then((p) => {
      if (!vigente) return;
      setResumen(Object.fromEntries(p.equipos.map((r) => [r.id, r])));
      setConsultado(p.consultado);
    }).catch(() => {});
    cargar();
    const id = window.setInterval(cargar, ruta ? 15000 : 5000);
    return () => { vigente = false; window.clearInterval(id); };
  }, [ruta]);

  const ir = useCallback((id: string | null) => { location.hash = id ? `#/equipo/${id}` : '#/'; }, []);
  const equipo = equipos?.find((e) => e.id === ruta) ?? null;

  if (errorReg) {
    return <div className="vacio" style={{ padding: 32 }}>No se pudo leer el registro de equipos (equipos.json): {errorReg}</div>;
  }
  if (!equipos) return <div className="vacio" style={{ padding: 32 }}>Cargando equipos…</div>;

  return (
    <div className={`shell ${navAbierta ? '' : 'nav-compacta'}`}>
      <aside className="nav" aria-label="Equipos del laboratorio">
        <div className="nav-cab">
          <button className="icono nav-toggle" onClick={() => setNavAbierta(!navAbierta)}
            aria-label={navAbierta ? 'Contraer navegación' : 'Expandir navegación'} title={navAbierta ? 'Contraer' : 'Expandir'}>
            {navAbierta ? '‹' : '›'}
          </button>
          {navAbierta && <div className="nav-titulo"><b>{org.campus ?? 'USS'}</b><small>{org.area}</small></div>}
        </div>
        <button className={`nav-item ${ruta === null ? 'on' : ''}`} onClick={() => ir(null)} title="Vista general">
          <span className="nav-ico">▦</span>{navAbierta && <span>Vista general</span>}
        </button>
        {navAbierta && <div className="nav-grupo">Aula {org.aula ?? '—'}</div>}
        {equipos.map((e) => {
          const sev = sevEquipo(resumen[e.id]);
          return (
            <button key={e.id} className={`nav-item ${ruta === e.id ? 'on' : ''}`} onClick={() => ir(e.id)}
              title={`${e.nombre} ${e.codigo} · ${TXT_SEV[sev]}`}>
              <span className={`nav-sem sev-${sev}`} />
              {navAbierta ? (
                <span className="nav-txt"><b>{e.proceso}</b><small>{e.codigo} · {e.plc.split(' ').slice(0, 3).join(' ')}</small></span>
              ) : <span className="nav-mini">{e.proceso.slice(0, 3)}</span>}
            </button>
          );
        })}
        {navAbierta && (
          <div className="nav-pie">
            <span>{equipos.length} equipo(s) registrados</span>
            <small>Para agregar un PLC: entrada en <code>equipos.json</code> + conector + servidor MCP + grafo.</small>
          </div>
        )}
      </aside>
      <div className="principal">
        {equipo ? (
          <VistaEquipo key={equipo.id} equipo={equipo} salud={salud} tema={tema} setTema={setTema}
            irAPlanta={() => ir(null)} aula={`Aula ${org.aula ?? ''}`.trim()} />
        ) : (
          <Planta org={org} equipos={equipos} resumen={resumen} consultado={consultado} salud={salud}
            tema={tema} setTema={setTema} abrir={(id) => ir(id)} />
        )}
      </div>
    </div>
  );
}
