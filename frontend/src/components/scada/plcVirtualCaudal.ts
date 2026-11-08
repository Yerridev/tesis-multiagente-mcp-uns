import { useCallback, useEffect, useRef, useState } from 'react';

/* ============================================================
   PLC VIRTUAL de Caudal (S7-200 simulado en el navegador)
   Solo se usa en modo SIMULADOR. Nunca envía nada al PLC real.
   - Hay que CONECTARSE primero (handshake simulado).
   - Enclavamientos para INICIAR (como en el módulo real):
       T1 sin nivel bajo · V5 y V2 abiertas · V1, V3, V4, V6, V7 cerradas · setpoint > 0
   - En marcha: PID (PI) sobre la bomba; el flujómetro sigue al setpoint
     con pequeñas variaciones (ruido + dinámica de la bomba).
   - Si un enclavamiento se pierde en marcha (p. ej. abres V6 o baja el nivel) → se detiene.
   ============================================================ */

export type EstadoConexion = 'desconectado' | 'conectando' | 'conectado';
export interface EntradasPlanta { valvulas: Record<string, boolean | null>; nivelPct: number | null; nivelBajo: boolean | null }
export interface Chequeo { id: string; texto: string; ok: boolean }
export interface MuestraSim { ts: string; value: number }

const DEBEN_ABIERTAS = ['V5', 'V2'];
const DEBEN_CERRADAS = ['V1', 'V3', 'V4', 'V6', 'V7'];
const PASO_MS = 200;

export function usePlcVirtualCaudal(activo: boolean, entradas: EntradasPlanta, aperturaValvulaPct: number) {
  const [conexion, setConexion] = useState<EstadoConexion>('desconectado');
  const [marcha, setMarcha] = useState(false);
  const [sp, setSpState] = useState(0);                 // L/min (0 = sin setpoint cargado)
  const [caudal, setCaudal] = useState(0);
  const [variador, setVariador] = useState(0);          // % salida PID
  const [mensaje, setMensaje] = useState('PLC virtual desconectado');
  const [historial, setHistorial] = useState<MuestraSim[]>([]);
  const st = useRef({ q: 0, u: 0, integ: 0 });

  // al salir del modo simulador se apaga todo
  useEffect(() => {
    if (!activo) { setConexion('desconectado'); setMarcha(false); setCaudal(0); setVariador(0); setHistorial([]); st.current = { q: 0, u: 0, integ: 0 }; setMensaje('PLC virtual desconectado'); }
  }, [activo]);

  const chequeos: Chequeo[] = [
    { id: 'con', texto: 'Conectado al PLC virtual', ok: conexion === 'conectado' },
    { id: 'nivel', texto: 'T1 sin nivel bajo', ok: entradas.nivelBajo === false },
    ...DEBEN_ABIERTAS.map((v) => ({ id: v, texto: `${v} abierta`, ok: entradas.valvulas[v] === true })),
    { id: 'cerradas', texto: `${DEBEN_CERRADAS.join(', ')} cerradas`, ok: DEBEN_CERRADAS.every((v) => entradas.valvulas[v] === false) },
    { id: 'sp', texto: 'Setpoint cargado (> 0 L/min)', ok: sp > 0 },
  ];
  const listo = chequeos.every((c) => c.ok);
  const enclavamientosMarcha = chequeos.filter((c) => c.id !== 'sp');

  const conectar = useCallback(() => {
    if (!activo || conexion !== 'desconectado') return;
    setConexion('conectando');
    setMensaje('Conectando con S7-200 virtual (127.0.0.1:102 · TSAP 10.00)…');
    window.setTimeout(() => { setConexion('conectado'); setMensaje('PLC virtual conectado · listo para recibir órdenes'); }, 1500);
  }, [activo, conexion]);

  const desconectar = useCallback(() => { setConexion('desconectado'); setMarcha(false); setMensaje('PLC virtual desconectado'); }, []);

  const cargarSetpoint = useCallback((v: number) => {
    if (conexion !== 'conectado') { setMensaje('Setpoint no enviado: primero conecta el PLC virtual'); return; }
    setSpState(Math.max(0, Math.min(140, v)));
    setMensaje(`Setpoint ${v.toFixed(1)} L/min cargado en el PLC virtual`);
  }, [conexion]);

  const iniciar = useCallback(() => {
    const fallan = chequeos.filter((c) => !c.ok);
    if (fallan.length) { setMensaje('No inicia: ' + fallan.map((c) => c.texto).join(' · ')); return false; }
    setMarcha(true);
    setMensaje(`En marcha · PID llevando el caudal a ${sp.toFixed(1)} L/min`);
    return true;
  }, [chequeos, sp]);

  const detener = useCallback(() => { setMarcha(false); setMensaje('Detenido por el operador'); }, []);

  // pérdida de enclavamientos en marcha → paro
  const fallaMarcha = marcha ? enclavamientosMarcha.find((c) => !c.ok) : undefined;
  useEffect(() => {
    if (fallaMarcha) { setMarcha(false); setMensaje(`Paro por enclavamiento: ${fallaMarcha.texto} ya no se cumple`); }
  }, [fallaMarcha?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // dinámica: bomba + válvula proporcional + PI
  useEffect(() => {
    if (!activo || conexion !== 'conectado') return;
    const id = window.setInterval(() => {
      const s = st.current;
      const dt = PASO_MS / 1000;
      const qMax = 140 * Math.sqrt(Math.max(0.05, aperturaValvulaPct / 100));   // caudal máx. según la válvula
      if (marcha) {
        const e = (sp - s.q) / 140;
        s.integ = Math.max(-1, Math.min(1.2, s.integ + e * dt / 4));
        const uObjetivo = Math.max(0, Math.min(1, 1.4 * e + s.integ));
        s.u += Math.max(-0.06 * dt, Math.min(0.06 * dt, uObjetivo - s.u));   // rampa del variador: ~6 %/s
      } else {
        s.integ = 0;
        s.u = Math.max(0, s.u - 0.08 * dt);                                   // parada en rampa (desaceleración)
      }
      const objetivo = s.u * qMax;
      s.q += (objetivo - s.q) * Math.min(1, dt / 3);                           // inercia hidráulica (τ ≈ 3 s)
      const ruido = marcha && s.q > 1 ? (Math.random() - 0.5) * 0.8 + Math.sin(Date.now() / 900) * 0.25 : 0;
      const q = Math.max(0, s.q + ruido);
      setCaudal(q);
      setVariador(s.u * 100);
      setHistorial((h) => [...h, { ts: new Date().toISOString(), value: q }].slice(-300));
    }, PASO_MS);
    return () => window.clearInterval(id);
  }, [activo, conexion, marcha, sp, aperturaValvulaPct]);

  return { conexion, conectar, desconectar, marcha, iniciar, detener, sp, cargarSetpoint, caudal, variador, mensaje, chequeos, listo, historial };
}
