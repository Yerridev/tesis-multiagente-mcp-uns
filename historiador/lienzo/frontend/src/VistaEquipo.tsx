import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow, useNodesState,
  type Connection, type Edge, type Node, type NodeTypes, type EdgeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { apiEquipo, fmtHora, isoLima } from './api';
import { Ctx, resalteDe, vacio, type Estado, type Resalte } from './ctx';
import { AccCtx } from './acciones';
import EquipoNode from './nodes/EquipoNode';
import PanelNode from './nodes/PanelNode';
import RelacionEdge from './edges/RelacionEdge';
import TimeBar from './TimeBar';
import { ModalNodo, ModalRelacion } from './Editor';
import { IcoCandado, IcoEditar, IcoLuna, IcoSol } from './icons';
import type { Arista, Diagnostico, Enlace, EquipoCfg, EventoLinea, Grafo, NodoGrafo, Relacion, Salud, Valor } from './types';

const nodeTypes: NodeTypes = { equipo: EquipoNode, panel: PanelNode };
const edgeTypes: EdgeTypes = { relacion: RelacionEdge };
const PANELES: [string, number, number][] = [['diagnostico', 400, 470], ['agente', 400, 560], ['tendencia', 820, 330], ['uns', 400, 330]];
const ANCHO_EQ = 236;

function lados(a: Node | undefined, b: Node | undefined): [string, string] {
  if (!a || !b) return ['s-right', 't-left'];
  const dx = b.position.x - a.position.x;
  const dy = b.position.y - a.position.y;
  if (Math.abs(dx) >= Math.abs(dy) * 1.2) return dx >= 0 ? ['s-right', 't-left'] : ['s-left', 't-right'];
  return dy >= 0 ? ['s-bottom', 't-top'] : ['s-top', 't-bottom'];
}

interface Props {
  equipo: EquipoCfg;
  salud: Salud | null;
  tema: 'oscuro' | 'claro';
  setTema: (t: 'oscuro' | 'claro') => void;
  irAPlanta: () => void;
  aula?: string;
}

/** Lienzo vivo de UN equipo: la misma plantilla para todos; lo especifico viene del registro y del grafo. */
export default function VistaEquipo({ equipo, salud, tema, setTema, irAPlanta, aula }: Props) {
  const api = useMemo(() => apiEquipo(equipo.id), [equipo.id]);
  const [grafoSrv, setGrafoSrv] = useState<Grafo | null>(null);
  const [grafo, setGrafo] = useState<Grafo | null>(null); // copia de trabajo (edicion)
  const [editando, setEditando] = useState(false);
  const [sucio, setSucio] = useState(false);
  const [vivoVals, setVivoVals] = useState<Record<string, Valor>>({});
  const [histVals, setHistVals] = useState<Record<string, Valor>>({});
  const [enlace, setEnlace] = useState<Enlace | null>(null);
  const [momento, setMomento] = useState<string | null>(null);
  const [diag, setDiag] = useState<Diagnostico | null>(null);
  const [resAgente, setResAgente] = useState<{ r: Resalte; hasta: number } | null>(null);
  const [tocando, setTocando] = useState<{ nodos: Set<string>; hasta: number }>({ nodos: new Set(), hasta: 0 });
  const [ahora, setAhora] = useState(Date.now());
  const [desde, setDesde] = useState(Date.now() - 4 * 3600e3);
  const [eventos, setEventos] = useState<EventoLinea[]>([]);
  const [aviso, setAviso] = useState<{ txt: string; tipo: 'ok' | 'err' } | null>(null);
  const [modalRel, setModalRel] = useState<{ de: string; a: string; idx?: number } | null>(null);
  const [modalNodo, setModalNodo] = useState<{ id?: string } | null>(null);
  const [variablesUns, setVariablesUns] = useState<string[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const wsRef = useRef<WebSocket | null>(null);

  // ---------- carga inicial
  useEffect(() => {
    api.grafo().then((g) => { setGrafoSrv(g); setGrafo(g); }).catch((e) => setAviso({ txt: `No se pudo leer el grafo: ${e}`, tipo: 'err' }));
    api.variables().then((v) => setVariablesUns(v.variables.map((x) => x.variable))).catch(() => {});
    api.rango().then((r) => { if (r.desde) setDesde(Math.max(Date.parse(r.desde), Date.now() - 4 * 3600e3)); }).catch(() => {});
    const id = window.setInterval(() => { setAhora(Date.now()); }, 2000);
    return () => { window.clearInterval(id); };
  }, [api]);

  // ---------- en vivo: WebSocket del UNS de este equipo
  useEffect(() => {
    let cerrado = false;
    let reintento: number | undefined;
    const conectar = () => {
      const ws = new WebSocket(api.wsUrl());
      wsRef.current = ws;
      ws.onmessage = (m) => {
        const ev = JSON.parse(m.data);
        if (ev.tipo === 'snapshot') {
          setVivoVals(ev.valores ?? {});
          setEnlace(ev.enlace ?? null);
        } else if (ev.tipo === 'valor') {
          setVivoVals((v) => ({ ...v, [ev.variable]: { valor: ev.valor, unidad: ev.unidad, t: ev.t } }));
        } else if (ev.tipo === 'evento') {
          setEnlace((e) => {
            const b: Enlace = e ?? { datos_en_vivo: true, conector_edge: null, conexion_plc: null, ultimo_latido: null, segundos_desde_latido: null, motivos: [] };
            if (ev.variable === 'edge/estado') return { ...b, conector_edge: ev.texto };
            if (ev.variable === 'plc/conexion') return { ...b, conexion_plc: ev.texto };
            if (ev.variable === 'edge/heartbeat') return { ...b, ultimo_latido: ev.t };
            return b;
          });
        }
      };
      ws.onclose = () => { if (!cerrado) reintento = window.setTimeout(conectar, 2000); };
    };
    conectar();
    return () => { cerrado = true; window.clearTimeout(reintento); wsRef.current?.close(); };
  }, [api]);

  // ---------- historico (maquina del tiempo) y diagnostico
  useEffect(() => {
    let vigente = true;
    const t = window.setTimeout(() => {
      if (momento) api.estado(momento).then((e) => { if (vigente) setHistVals(e.valores); }).catch(() => {});
      api.diagnostico(momento ?? undefined).then((d) => { if (vigente) setDiag(d); }).catch(() => {});
    }, momento ? 250 : 0);
    const poll = momento ? undefined : window.setInterval(() => api.diagnostico().then((d) => { if (vigente) setDiag(d); }).catch(() => {}), 5000);
    return () => { vigente = false; window.clearTimeout(t); if (poll) window.clearInterval(poll); };
  }, [momento, api]);

  useEffect(() => {
    const cargar = () => api.eventos(isoLima(desde), isoLima(Date.now())).then(setEventos).catch(() => {});
    cargar();
    const id = window.setInterval(cargar, 30000);
    return () => window.clearInterval(id);
  }, [desde, api]);

  // ---------- nodos del lienzo
  useEffect(() => {
    if (!grafo) return;
    setNodes((prev) => {
      const posPrev = Object.fromEntries(prev.map((n) => [n.id, n.position]));
      const L = grafo.layout ?? {};
      const eqs: Node[] = Object.entries(grafo.nodos).map(([id, n], i) => ({
        id, type: 'equipo', data: { nodo: n },
        position: posPrev[id] ?? (L[id] ? { x: L[id][0], y: L[id][1] } : { x: -320, y: 120 + i * 40 }),
        style: { width: ANCHO_EQ },
      }));
      const pans: Node[] = PANELES.map(([k, w, h]) => ({
        id: `panel:${k}`, type: 'panel', dragHandle: '.panel-head',
        data: { kind: k, agenteHabilitado: salud?.agente, modelo: salud?.modelo },
        position: posPrev[`panel:${k}`] ?? (L[`panel:${k}`] ? { x: L[`panel:${k}`][0], y: L[`panel:${k}`][1] } : { x: 1300, y: 0 }),
        style: { width: w, height: h },
      }));
      return [...eqs, ...pans];
    });
  }, [grafo, salud?.agente, salud?.modelo, setNodes]);

  const porId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const edges: Edge[] = useMemo(() => (grafo?.relaciones ?? []).map((r, i) => {
    const [sh, th] = lados(porId[r.de], porId[r.a]);
    return { id: `${r.de}|${r.rel}|${r.a}`, source: r.de, target: r.a, sourceHandle: sh, targetHandle: th,
      type: 'relacion', data: { rel: r.rel, nota: r.nota, idx: i } };
  }), [grafo, porId]);

  // ---------- resaltes
  const resalte: Resalte = useMemo(() => {
    if (resAgente && resAgente.hasta > ahora) return resAgente.r;
    return resalteDe(diag);
  }, [resAgente, diag, ahora]);
  const agenteTocando = tocando.hasta > ahora ? tocando.nodos : new Set<string>();

  const nodosDeVariables = useCallback((vars: string[]) => {
    if (!grafo) return [];
    const cortas = vars.map((v) => v.replace(equipo.prefijo_db, ''));
    return Object.entries(grafo.nodos).filter(([, n]) => n.variables.some((v) => cortas.includes(v))).map(([id]) => id);
  }, [grafo, equipo.prefijo_db]);

  const acciones = useMemo(() => ({
    agenteToca: (ns: string[]) => setTocando({ nodos: new Set(ns), hasta: Date.now() + 5000 }),
    agenteCadena: (ar: Arista[]) => {
      const aristas = new Set(ar.map((x) => `${x.de}|${x.a}`));
      const nodos = new Set(ar.flatMap((x) => [x.de, x.a]));
      setResAgente({ r: { aristas, nodos, fuente: 'agente' }, hasta: Date.now() + 25000 });
    },
    irA: setMomento,
    nodosDeVariables,
  }), [nodosDeVariables]);

  const enlaceVivo: Enlace | null = useMemo(() => {
    if (!enlace) return null;
    const edad = enlace.ultimo_latido ? (ahora - Date.parse(enlace.ultimo_latido)) / 1000 : null;
    return { ...enlace, segundos_desde_latido: edad, datos_en_vivo: Boolean(edad !== null && edad < 30 && enlace.conexion_plc === 'CONECTADO') };
  }, [enlace, ahora]);

  const estado: Estado = {
    equipo, grafo, valores: momento ? histVals : vivoVals, enlace: momento ? null : enlaceVivo, diag, momento,
    resalte: resalte ?? vacio, agenteTocando, editando, tema,
  };

  // ---------- edicion del grafo
  const cambiarGrafo = (f: (g: Grafo) => Grafo) => { setGrafo((g) => (g ? f(g) : g)); setSucio(true); };
  const onConnect = useCallback((c: Connection) => {
    if (!editando || !c.source || !c.target || c.source.startsWith('panel:') || c.target.startsWith('panel:') || c.source === c.target) return;
    setModalRel({ de: c.source, a: c.target });
  }, [editando]);
  const guardar = async () => {
    if (!grafo) return;
    const layout: Record<string, [number, number]> = Object.fromEntries(nodes.map((n) => [n.id, [Math.round(n.position.x), Math.round(n.position.y)]]));
    try {
      const r = await api.guardarGrafo({ nodos: grafo.nodos, relaciones: grafo.relaciones, layout });
      const g = await api.grafo();
      setGrafoSrv(g); setGrafo(g); setSucio(false); setEditando(false);
      setAviso({ txt: `Grafo guardado · respaldo en ${r.respaldo}. El diagnóstico ya usa la nueva versión.`, tipo: 'ok' });
    } catch (e) {
      setAviso({ txt: `No se guardó: ${String((e as Error).message)}`, tipo: 'err' });
    }
  };
  const descartar = () => { setGrafo(grafoSrv); setNodes([]); setSucio(false); setEditando(false); };
  useEffect(() => { if (aviso) { const t = window.setTimeout(() => setAviso(null), 6000); return () => window.clearTimeout(t); } }, [aviso]);

  const nombres = useMemo(() => Object.fromEntries(Object.entries(grafo?.nodos ?? {}).map(([k, n]) => [k, n.nombre])), [grafo]);
  const modo = (vivoVals['estado/selector_remoto']?.valor ? 'REMOTO' : vivoVals['estado/selector_local']?.valor ? 'LOCAL' : 'EN 0');

  return (
    <Ctx.Provider value={estado}>
      <AccCtx.Provider value={acciones}>
        <div className={`app ${editando ? 'modo-edicion' : ''}`}>
          <header className="barra">
            <div className="marca">
              <div className="logo" aria-hidden="true"><span /><span /><span /></div>
              <div>
                <nav className="migas" aria-label="Ubicación">
                  <button className="miga" onClick={irAPlanta}>{aula ?? 'Laboratorio'}</button>
                  <span>›</span>
                  <b>{equipo.nombre}</b>
                </nav>
                <h1>{equipo.nombre} · {equipo.codigo}</h1>
                <p title={`${equipo.plc} · ${equipo.ip} · ${equipo.protocolo}`}>{equipo.plc} · {equipo.ip} · {equipo.protocolo}</p>
              </div>
            </div>
            <div className="estados">
              <Pill ok={salud?.db} txt="Historiador" />
              <Pill ok={salud?.mqtt} txt="UNS / MQTT" />
              <Pill ok={enlaceVivo?.conector_edge === 'ONLINE' && (enlaceVivo?.segundos_desde_latido ?? 99) < 30} txt="Conector" />
              <Pill ok={enlaceVivo?.conexion_plc === 'CONECTADO'} txt="PLC" />
              <span className={`pill modo modo-${modo.toLowerCase().replace(' ', '')}`}>{modo}</span>
              <span className="pill ro" title="Ninguna parte del lienzo puede escribir en el PLC"><IcoCandado /> Solo lectura</span>
            </div>
            <div className="acciones">
              {!editando && <button onClick={() => setEditando(true)}><IcoEditar /> Editar grafo</button>}
              {editando && (
                <>
                  <button onClick={() => setModalNodo({})}>+ Nodo</button>
                  <button onClick={descartar}>Descartar</button>
                  <button className="primario" onClick={guardar}>Guardar grafo</button>
                </>
              )}
              <button className="icono" onClick={() => setTema(tema === 'oscuro' ? 'claro' : 'oscuro')} aria-label="Cambiar tema">
                {tema === 'oscuro' ? <IcoSol /> : <IcoLuna />}
              </button>
            </div>
          </header>
          {editando && (
            <div className="banda-edicion">
              Modo edición del knowledge graph de {equipo.codigo}: arrastra desde un borde de un nodo a otro para crear una relación · clic en una relación para editarla · doble clic en un nodo para editarlo · Supr elimina lo seleccionado.
              {sucio && <b> Cambios sin guardar.</b>}
            </div>
          )}
          {momento && (
            <div className="banda-hist">Reproduciendo el historial a las <b>{fmtHora(momento)}</b> · los valores y el diagnóstico corresponden a ese momento</div>
          )}
          <main className="lienzo">
            <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
              <defs>
                <marker id="flecha-normal" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0 0L10 5L0 10z" className="flecha-normal" />
                </marker>
                <marker id="flecha-cadena" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0 0L10 5L0 10z" className="flecha-cadena" />
                </marker>
              </defs>
            </svg>
            <ReactFlow
              nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
              onNodesChange={(ch) => {
                const borrados = ch.filter((c) => c.type === 'remove').map((c) => (c as { id: string }).id).filter((id) => !id.startsWith('panel:'));
                if (borrados.length && editando) {
                  cambiarGrafo((g) => {
                    const nodos = { ...g.nodos };
                    borrados.forEach((id) => delete nodos[id]);
                    return { ...g, nodos, relaciones: g.relaciones.filter((r) => !borrados.includes(r.de) && !borrados.includes(r.a)) };
                  });
                }
                onNodesChange(ch.filter((c) => c.type !== 'remove' || (editando && !(c as { id: string }).id.startsWith('panel:'))));
                if (editando && ch.some((c) => c.type === 'position')) setSucio(true);
              }}
              onEdgesChange={(ch) => {
                if (!editando) return;
                const ids = ch.filter((c) => c.type === 'remove').map((c) => (c as { id: string }).id);
                if (ids.length) cambiarGrafo((g) => ({ ...g, relaciones: g.relaciones.filter((r) => !ids.includes(`${r.de}|${r.rel}|${r.a}`)) }));
              }}
              onConnect={onConnect}
              onEdgeClick={(_, e) => { if (editando) setModalRel({ de: e.source, a: e.target, idx: (e.data as { idx: number }).idx }); }}
              onNodeDoubleClick={(_, n) => { if (editando && n.type === 'equipo') setModalNodo({ id: n.id }); }}
              nodesConnectable={editando} edgesFocusable={editando} deleteKeyCode={editando ? ['Delete', 'Backspace'] : null}
              fitView fitViewOptions={{ padding: 0.08 }} minZoom={0.2} maxZoom={1.8} proOptions={{ hideAttribution: true }}
              colorMode={tema === 'oscuro' ? 'dark' : 'light'}
            >
              <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable nodeStrokeWidth={2} nodeColor={(n) => (n.type === 'panel' ? 'var(--minimap-panel)' : 'var(--minimap-eq)')} />
            </ReactFlow>
            <div className="leyenda">
              <span><i className="l-flujo" />flujo de proceso</span>
              <span><i className="l-rel" />relación del grafo</span>
              <span><i className="l-cadena" />cadena causal del diagnóstico</span>
              <span><i className="l-agente" />consultado por el agente</span>
            </div>
            {aviso && <div className={`aviso ${aviso.tipo}`}>{aviso.txt}</div>}
          </main>
          <TimeBar momento={momento} desde={desde} hasta={ahora} eventos={eventos} marcas={equipo.eventos ?? {}} onCambio={setMomento} />
        </div>
        {modalRel && grafo && (
          <ModalRelacion de={modalRel.de} a={modalRel.a} nombres={nombres}
            rel={modalRel.idx !== undefined ? grafo.relaciones[modalRel.idx]?.rel : undefined}
            nota={modalRel.idx !== undefined ? grafo.relaciones[modalRel.idx]?.nota : undefined}
            onCerrar={() => setModalRel(null)}
            onBorrar={modalRel.idx !== undefined ? () => { const i = modalRel.idx!; cambiarGrafo((g) => ({ ...g, relaciones: g.relaciones.filter((_, k) => k !== i) })); setModalRel(null); } : undefined}
            onGuardar={(rel, nota) => {
              const nueva: Relacion = { de: modalRel.de, rel, a: modalRel.a, ...(nota ? { nota } : {}) };
              cambiarGrafo((g) => {
                const rs = [...g.relaciones];
                if (modalRel.idx !== undefined) rs[modalRel.idx] = nueva; else rs.push(nueva);
                return { ...g, relaciones: rs };
              });
              setModalRel(null);
            }} />
        )}
        {modalNodo && grafo && (
          <ModalNodo existentes={Object.keys(grafo.nodos)} variables={variablesUns} idInicial={modalNodo.id}
            inicial={modalNodo.id ? grafo.nodos[modalNodo.id] : undefined}
            onCerrar={() => setModalNodo(null)}
            onBorrar={modalNodo.id ? () => { const id = modalNodo.id!; cambiarGrafo((g) => { const nodos = { ...g.nodos }; delete nodos[id]; return { ...g, nodos, relaciones: g.relaciones.filter((r) => r.de !== id && r.a !== id) }; }); setModalNodo(null); } : undefined}
            onGuardar={(id, n: NodoGrafo) => {
              cambiarGrafo((g) => ({ ...g, nodos: { ...g.nodos, [id]: n }, layout: { ...(g.layout ?? {}), ...(g.nodos[id] ? {} : { [id]: [-320, 380] as [number, number] }) } }));
              setModalNodo(null);
            }} />
        )}
      </AccCtx.Provider>
    </Ctx.Provider>
  );
}

export function Pill({ ok, txt }: { ok: boolean | undefined; txt: string }) {
  return <span className={`pill ${ok === undefined ? 'nd' : ok ? 'ok' : 'mal'}`}><span className="punto" />{txt}</span>;
}
