import { useCallback, useEffect, useRef, useState } from 'react';

/* ============================================================
   PLC VIRTUAL de Nivel (MicroLogix 1100 simulado en el navegador)
   Solo en modo SIMULADOR. Nunca envía nada al PLC real.
   - Conectar primero (handshake simulado).
   - Enclavamientos para INICIAR:
       T1 ni en nivel alto ni en nivel bajo · solo V4 abierta (V1, V2, V3, V5, VF, V7 cerradas) · setpoint > 0
   - En marcha: la bomba pasa agua de T1 a T2 por V4; un PI ajusta la bomba para
     llevar T2 al setpoint; T2 descarga a T1 por la válvula proporcional (perturbación).
   - VF abierta llena T1 desde la fuente externa. Se detiene si se pierde un enclavamiento.
   ============================================================ */

export type EstadoConexion = 'desconectado' | 'conectando' | 'conectado';
export interface Chequeo { id: string; texto: string; ok: boolean }
export interface MuestraSim { ts: string; value: number }

export const T1_ALTO = 85;   // % (switch de nivel alto)
export const T1_BAJO = 15;   // % (switch de nivel bajo)
const ALTO_T2 = 60;          // cm
const SOLO_ABIERTA = 'V4';
const DEBEN_CERRADAS = ['V1', 'V2', 'V3', 'V5', 'VF', 'V7'];
const PASO_MS = 200;

export function usePlcVirtualNivel(activo: boolean, valvulas: Record<string, boolean | null>, aperturaVpPct: number) {
  const [conexion, setConexion] = useState<EstadoConexion>('desconectado');
  const [marcha, setMarcha] = useState(false);
  const [sp, setSp] = useState(0);
  const [t1, setT1] = useState(5);        // % del reservorio (empieza casi vacío → nivel bajo)
  const [t2, setT2] = useState(0);        // cm en el tanque de proceso
  const [bombaPct, setBombaPct] = useState(0);
  const [mensaje, setMensaje] = useState('PLC virtual desconectado');
  const [historial, setHistorial] = useState<MuestraSim[]>([]);
  const st = useRef({ u: 0, integ: 0, t1: 5, t2: 0 });

  useEffect(() => {
    if (!activo) {
      setConexion('desconectado'); setMarcha(false); setSp(0); setT1(5); setT2(0); setBombaPct(0); setHistorial([]);
      st.current = { u: 0, integ: 0, t1: 5, t2: 0 }; setMensaje('PLC virtual desconectado');
    }
  }, [activo]);

  const t1Alto = t1 >= T1_ALTO;
  const t1Bajo = t1 <= T1_BAJO;
  const chequeos: Chequeo[] = [
    { id: 'con', texto: 'Conectado al PLC virtual', ok: conexion === 'conectado' },
    { id: 't1', texto: 'T1 sin nivel alto ni nivel bajo', ok: !t1Alto && !t1Bajo },
    { id: 'v4', texto: `${SOLO_ABIERTA} abierta`, ok: valvulas[SOLO_ABIERTA] === true },
    { id: 'cerradas', texto: `${DEBEN_CERRADAS.join(', ')} cerradas`, ok: DEBEN_CERRADAS.every((v) => valvulas[v] === false) },
    { id: 'sp', texto: 'Setpoint cargado (> 0 cm)', ok: sp > 0 },
  ];
  const listo = chequeos.every((c) => c.ok);

  const conectar = useCallback(() => {
    if (!activo || conexion !== 'desconectado') return;
    setConexion('conectando');
    setMensaje('Conectando con MicroLogix 1100 virtual (127.0.0.1:44818)…');
    window.setTimeout(() => { setConexion('conectado'); setMensaje('PLC virtual conectado · listo para recibir órdenes'); }, 1500);
  }, [activo, conexion]);
  const desconectar = useCallback(() => { setConexion('desconectado'); setMarcha(false); setMensaje('PLC virtual desconectado'); }, []);

  const cargarSetpoint = useCallback((v: number) => {
    if (conexion !== 'conectado') { setMensaje('Setpoint no enviado: primero conecta el PLC virtual'); return; }
    setSp(Math.max(0, Math.min(ALTO_T2, v)));
    setMensaje(`Setpoint ${v.toFixed(1)} cm cargado en el PLC virtual`);
  }, [conexion]);

  const iniciar = useCallback(() => {
    const fallan = chequeos.filter((c) => !c.ok);
    if (fallan.length) { setMensaje('No inicia: ' + fallan.map((c) => c.texto).join(' · ')); return false; }
    setMarcha(true); setMensaje(`En marcha · PID llevando T2 a ${sp.toFixed(1)} cm`);
    return true;
  }, [chequeos, sp]);
  const detener = useCallback(() => { setMarcha(false); setMensaje('Detenido por el operador'); }, []);

  const falla = marcha ? chequeos.find((c) => c.id !== 'sp' && c.id !== 't1' && !c.ok) ?? (t1Bajo ? chequeos[1] : undefined) : undefined;
  useEffect(() => {
    if (falla) { setMarcha(false); setMensaje(`Paro por enclavamiento: ${falla.texto} ya no se cumple`); }
  }, [falla?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // dinámica de los dos tanques
  const v6 = valvulas.VF === true;
  const v7 = valvulas.V7 === true;   // descarga de T1 al desagüe
  useEffect(() => {
    if (!activo) return;
    const id = window.setInterval(() => {
      const s = st.current, dt = PASO_MS / 1000;
      if (marcha && conexion === 'conectado') {
        const e = (sp - s.t2) / ALTO_T2;
        const uObj = Math.max(0, Math.min(1, 3 * e + s.integ));
        const limitado = Math.abs(uObj - s.u) > 0.08 * dt;
        if (!limitado) s.integ = Math.max(-0.5, Math.min(1, s.integ + e * dt / 3));
        s.u += Math.max(-0.08 * dt, Math.min(0.08 * dt, uObj - s.u));
      } else { s.integ = 0; s.u = Math.max(0, s.u - 0.1 * dt); }
      const entraT2 = s.u * 1.6 * (s.t1 > 2 ? 1 : 0);                         // cm/s que aporta la bomba
      const saleT2 = 0.32 * (aperturaVpPct / 100) * Math.sqrt(Math.max(0, s.t2));  // cm/s por la proporcional
      s.t2 = Math.max(0, Math.min(ALTO_T2, s.t2 + (entraT2 - saleT2) * dt));
      s.t1 = Math.max(0, Math.min(100, s.t1 + (-entraT2 + saleT2) * 0.25 * dt + (v6 ? 2.2 * dt : 0) - (v7 ? 2.5 * dt : 0)));
      const ruido = s.t2 > 0.5 ? (Math.random() - 0.5) * 0.15 : 0;
      setT1(s.t1); setT2(Math.max(0, s.t2 + ruido)); setBombaPct(s.u * 100);
      if (conexion === 'conectado') setHistorial((h) => [...h, { ts: new Date().toISOString(), value: s.t2 }].slice(-300));
    }, PASO_MS);
    return () => window.clearInterval(id);
  }, [activo, marcha, conexion, sp, aperturaVpPct, v6, v7]);

  return { conexion, conectar, desconectar, marcha, iniciar, detener, sp, cargarSetpoint, t1, t2, t1Alto, t1Bajo, bombaPct, mensaje, chequeos, listo, historial };
}
