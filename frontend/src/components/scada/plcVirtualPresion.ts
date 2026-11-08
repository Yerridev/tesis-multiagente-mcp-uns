import { useCallback, useEffect, useRef, useState } from 'react';

/* ============================================================
   PLC VIRTUAL de Presión (NI cFP-2200 simulado en el navegador)
   Solo en modo SIMULADOR. Nunca envía nada al PLC real.
   - Conectar primero (handshake simulado).
   - Enclavamientos para INICIAR:
       T1 ni en nivel alto ni en nivel bajo · V2 y V5 abiertas
       (V1, V3, V4, V6, V7, VF cerradas) · setpoint > 0
   - En marcha: la bomba toma agua de T1 y la empuja por V5 al T2 (cámara de aire);
     un PI ajusta el variador para llevar la presión al setpoint; T2 descarga a T1
     por la válvula proporcional y V2 (perturbación).
   - VF + V1 abiertas llenan T1 desde la fuente; V7 lo vacía (con el sistema detenido). Se detiene si se pierde un enclavamiento.
   ============================================================ */

export type EstadoConexion = 'desconectado' | 'conectando' | 'conectado';
export interface Chequeo { id: string; texto: string; ok: boolean }
export interface MuestraSim { ts: string; value: number }

export const T1_ALTO = 85;
export const T1_BAJO = 15;
export const PSI_MAX = 60;
const DEBEN_ABIERTAS = ['V2', 'V5'];
const DEBEN_CERRADAS = ['V1', 'V3', 'V4', 'V6', 'V7', 'VF'];
const PASO_MS = 200;

export function usePlcVirtualPresion(activo: boolean, valvulas: Record<string, boolean | null>, aperturaVpPct: number) {
  const [conexion, setConexion] = useState<EstadoConexion>('desconectado');
  const [marcha, setMarcha] = useState(false);
  const [sp, setSp] = useState(0);
  const [t1, setT1] = useState(5);
  const [psi, setPsi] = useState(0);
  const [variador, setVariador] = useState(0);
  const [mensaje, setMensaje] = useState('PLC virtual desconectado');
  const [historial, setHistorial] = useState<MuestraSim[]>([]);
  const st = useRef({ u: 0, integ: 0, t1: 5, p: 0 });

  useEffect(() => {
    if (!activo) {
      setConexion('desconectado'); setMarcha(false); setSp(0); setT1(5); setPsi(0); setVariador(0); setHistorial([]);
      st.current = { u: 0, integ: 0, t1: 5, p: 0 }; setMensaje('PLC virtual desconectado');
    }
  }, [activo]);

  const t1Alto = t1 >= T1_ALTO;
  const t1Bajo = t1 <= T1_BAJO;
  const chequeos: Chequeo[] = [
    { id: 'con', texto: 'Conectado al PLC virtual', ok: conexion === 'conectado' },
    { id: 't1', texto: 'T1 sin nivel alto ni nivel bajo', ok: !t1Alto && !t1Bajo },
    { id: 'abiertas', texto: `${DEBEN_ABIERTAS.join(' y ')} abiertas`, ok: DEBEN_ABIERTAS.every((v) => valvulas[v] === true) },
    { id: 'cerradas', texto: `${DEBEN_CERRADAS.join(', ')} cerradas`, ok: DEBEN_CERRADAS.every((v) => valvulas[v] === false) },
    { id: 'sp', texto: 'Setpoint cargado (> 0 psi)', ok: sp > 0 },
  ];
  const listo = chequeos.every((c) => c.ok);

  const conectar = useCallback(() => {
    if (!activo || conexion !== 'desconectado') return;
    setConexion('conectando');
    setMensaje('Conectando con cFP-2200 virtual (127.0.0.1)…');
    window.setTimeout(() => { setConexion('conectado'); setMensaje('PLC virtual conectado · listo para recibir órdenes'); }, 1500);
  }, [activo, conexion]);
  const desconectar = useCallback(() => { setConexion('desconectado'); setMarcha(false); setMensaje('PLC virtual desconectado'); }, []);

  const cargarSetpoint = useCallback((v: number) => {
    if (conexion !== 'conectado') { setMensaje('Setpoint no enviado: primero conecta el PLC virtual'); return; }
    const x = Math.max(0, Math.min(40, v));
    setSp(x);
    setMensaje(`Setpoint ${x.toFixed(1)} psi cargado en el PLC virtual`);
  }, [conexion]);

  const iniciar = useCallback(() => {
    const fallan = chequeos.filter((c) => !c.ok);
    if (fallan.length) { setMensaje('No inicia: ' + fallan.map((c) => c.texto).join(' · ')); return false; }
    setMarcha(true); setMensaje(`En marcha · PID llevando T2 a ${sp.toFixed(1)} psi`);
    return true;
  }, [chequeos, sp]);
  const detener = useCallback(() => { setMarcha(false); setMensaje('Detenido por el operador'); }, []);

  // en marcha: cualquier enclavamiento perdido (salvo nivel alto y setpoint) detiene la bomba
  const falla = marcha ? chequeos.find((c) => c.id !== 'sp' && c.id !== 't1' && !c.ok) ?? (t1Bajo ? chequeos[1] : undefined) : undefined;
  useEffect(() => {
    if (falla) { setMarcha(false); setMensaje(`Paro por enclavamiento: ${falla.texto} ya no se cumple`); }
  }, [falla?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const vf = valvulas.VF === true && valvulas.V1 === true;   // la fuente solo llena T1 si VF y V1 están abiertas
  const v7 = valvulas.V7 === true;
  const v2 = valvulas.V2 === true;
  const v3 = valvulas.V3 === true;
  useEffect(() => {
    if (!activo) return;
    const id = window.setInterval(() => {
      const s = st.current, dt = PASO_MS / 1000;
      if (marcha && conexion === 'conectado') {
        const e = (sp - s.p) / PSI_MAX;
        const uObj = Math.max(0, Math.min(1, 3 * e + s.integ));
        const limitado = Math.abs(uObj - s.u) > 0.08 * dt;
        if (!limitado) s.integ = Math.max(-0.5, Math.min(1, s.integ + e * dt / 3));
        s.u += Math.max(-0.08 * dt, Math.min(0.08 * dt, uObj - s.u));
      } else { s.integ = 0; s.u = Math.max(0, s.u - 0.15 * dt); }
      const entra = 6 * s.u * (s.t1 > 2 ? 1 : 0);                                         // psi/s que empuja la bomba
      const salida = (v2 || v3 ? 1 : 0) * 1.3 * (aperturaVpPct / 100) * Math.sqrt(Math.max(0, s.p));   // por la proporcional
      s.p = Math.max(0, Math.min(PSI_MAX, s.p + (entra - salida) * dt));
      const retornaT1 = v2 && !v3 ? salida : 0;
      s.t1 = Math.max(0, Math.min(100, s.t1 + ((retornaT1 - entra) / 6) * 0.2 * dt + (vf ? 2.2 * dt : 0) - (v7 ? 2.5 * dt : 0)));
      const ruido = s.p > 0.5 ? (Math.random() - 0.5) * 0.25 : 0;
      setT1(s.t1); setPsi(Math.max(0, s.p + ruido)); setVariador(s.u * 100);
      if (conexion === 'conectado') setHistorial((h) => [...h, { ts: new Date().toISOString(), value: s.p }].slice(-300));
    }, PASO_MS);
    return () => window.clearInterval(id);
  }, [activo, marcha, conexion, sp, aperturaVpPct, vf, v7, v2, v3]);

  return { conexion, conectar, desconectar, marcha, iniciar, detener, sp, cargarSetpoint, t1, psi, t1Alto, t1Bajo, variador, mensaje, chequeos, listo, historial };
}
