import { useCallback, useEffect, useRef, useState } from 'react';

/* ============================================================
   PLC VIRTUAL de Temperatura (Twido simulado en el navegador)
   Solo en modo SIMULADOR. Nunca envía nada al PLC real.
   Preparación (manual, con el sistema detenido):
     - VF + V1 abiertas → la fuente llena T1 (enfriamiento).
     - V2 abierta → T1 baja agua a T2 (principal).
     - V4 abierta → T2 se vacía al desagüe.
   Enclavamientos para INICIAR:
     conectado · T1 y T2 sin nivel alto ni bajo · V1, V2 y VF cerradas · setpoint cargado
   En marcha: se abren las válvulas-sensor TEMP. SALIDA y TEMP. ENTRADA;
     T2 → TEMP. SALIDA → bomba → T1 → TEMP. ENTRADA → T2 (agua más fría).
     El PI regula la resistencia de T2; el enfriador enfría T1 por el serpentín.
   ============================================================ */

export type EstadoConexion = 'desconectado' | 'conectando' | 'conectado';
export interface Chequeo { id: string; texto: string; ok: boolean }
export interface MuestraSim { ts: string; value: number }

export const N_ALTO = 85;
export const N_BAJO = 15;
const AMB = 22;
const DEBEN_CERRADAS = ['V1', 'V2', 'VF', 'V4'];
const PASO_MS = 200;
const INICIO = { u: 0, integ: 0, n1: 5, n2: 5, t1: AMB, t2: AMB };

export function usePlcVirtualTemp(activo: boolean, valvulas: Record<string, boolean | null>) {
  const [conexion, setConexion] = useState<EstadoConexion>('desconectado');
  const [marcha, setMarcha] = useState(false);
  const [sp, setSp] = useState(0);
  const [n1, setN1] = useState(INICIO.n1);
  const [n2, setN2] = useState(INICIO.n2);
  const [t1, setT1] = useState(AMB);
  const [t2, setT2] = useState(AMB);
  const [salida, setSalida] = useState(0);
  const [caudal, setCaudal] = useState(0);
  const [mensaje, setMensaje] = useState('PLC virtual desconectado');
  const [historial, setHistorial] = useState<MuestraSim[]>([]);
  const st = useRef({ ...INICIO });

  useEffect(() => {
    if (!activo) {
      setConexion('desconectado'); setMarcha(false); setSp(0); setN1(INICIO.n1); setN2(INICIO.n2); setT1(AMB); setT2(AMB);
      setSalida(0); setCaudal(0); setHistorial([]); st.current = { ...INICIO }; setMensaje('PLC virtual desconectado');
    }
  }, [activo]);

  const okNivel = (n: number) => n > N_BAJO && n < N_ALTO;
  const chequeos: Chequeo[] = [
    { id: 'con', texto: 'Conectado al PLC virtual', ok: conexion === 'conectado' },
    { id: 'n1', texto: 'T1 sin nivel alto ni nivel bajo', ok: okNivel(n1) },
    { id: 'n2', texto: 'T2 sin nivel alto ni nivel bajo', ok: okNivel(n2) },
    { id: 'cerradas', texto: `${DEBEN_CERRADAS.join(', ')} cerradas`, ok: DEBEN_CERRADAS.every((v) => valvulas[v] === false) },
    { id: 'sp', texto: 'Setpoint cargado (°C)', ok: sp > 0 },
  ];
  const listo = chequeos.every((c) => c.ok);

  const conectar = useCallback(() => {
    if (!activo || conexion !== 'desconectado') return;
    setConexion('conectando');
    setMensaje('Conectando con Twido virtual (127.0.0.1:502)…');
    window.setTimeout(() => { setConexion('conectado'); setMensaje('PLC virtual conectado · listo para recibir órdenes'); }, 1500);
  }, [activo, conexion]);
  const desconectar = useCallback(() => { setConexion('desconectado'); setMarcha(false); setMensaje('PLC virtual desconectado'); }, []);

  const cargarSetpoint = useCallback((v: number) => {
    if (conexion !== 'conectado') { setMensaje('Setpoint no enviado: primero conecta el PLC virtual'); return; }
    const x = Math.max(15, Math.min(50, v));
    setSp(x); setMensaje(`Setpoint ${x.toFixed(1)} °C cargado en el PLC virtual`);
  }, [conexion]);

  const iniciar = useCallback(() => {
    const fallan = chequeos.filter((c) => !c.ok);
    if (fallan.length) { setMensaje('No inicia: ' + fallan.map((c) => c.texto).join(' · ')); return false; }
    setMarcha(true); setMensaje(`En marcha · SP ${sp.toFixed(1)} °C`);
    return true;
  }, [chequeos, sp]);
  const detener = useCallback(() => { setMarcha(false); setMensaje('Detenido por el operador'); }, []);

  // en marcha: perder conexión, abrir V1/V2/VF o un nivel bajo detiene el proceso
  const falla = marcha
    ? chequeos.find((c) => (c.id === 'con' || c.id === 'cerradas') && !c.ok)
      ?? (n1 <= N_BAJO ? chequeos[1] : n2 <= N_BAJO ? chequeos[2] : undefined)
    : undefined;
  useEffect(() => {
    if (falla) { setMarcha(false); setMensaje(`Paro por enclavamiento: ${falla.texto} ya no se cumple`); }
  }, [falla?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const llenaT1 = valvulas.VF === true && valvulas.V1 === true;
  const bajaT2 = valvulas.V2 === true;
  const vaciaT2 = valvulas.V4 === true;   // V4: descarga de T2 al desagüe
  useEffect(() => {
    if (!activo) return;
    const id = window.setInterval(() => {
      const s = st.current, dt = PASO_MS / 1000;
      const enMarcha = marcha && conexion === 'conectado';
      // niveles (preparación manual)
      if (llenaT1) s.n1 = Math.min(100, s.n1 + 2.2 * dt);
      if (bajaT2 && s.n1 > 0 && s.n2 < 100) { const q = Math.min(2 * dt, s.n1, 100 - s.n2); s.n1 -= q; s.n2 += q; }
      if (vaciaT2) s.n2 = Math.max(0, s.n2 - 2.5 * dt);
      // PI de la resistencia (T2)
      if (enMarcha) {
        const e = (sp - s.t2) / 35;
        const uObj = Math.max(0, Math.min(1, 2.5 * e + s.integ));
        const limitado = Math.abs(uObj - s.u) > 0.1 * dt;
        if (!limitado) s.integ = Math.max(-0.5, Math.min(1, s.integ + e * dt / 20));
        s.u += Math.max(-0.1 * dt, Math.min(0.1 * dt, uObj - s.u));
      } else { s.integ = 0; s.u = Math.max(0, s.u - 0.2 * dt); }
      // térmica: resistencia en T2, enfriador en T1, mezcla por la recirculación
      const mezcla = enMarcha ? 0.02 : 0;
      const frio = enMarcha ? 0.006 : 0;
      const d2 = 0.25 * s.u + mezcla * (s.t1 - s.t2) - 0.002 * (s.t2 - AMB);
      const d1 = -frio * (s.t1 - 12) + mezcla * (s.t2 - s.t1) - 0.002 * (s.t1 - AMB);
      s.t2 += d2 * dt; s.t1 += d1 * dt;
      const r = () => (Math.random() - 0.5) * 0.08;
      setN1(s.n1); setN2(s.n2); setT1(s.t1 + r()); setT2(s.t2 + r()); setSalida(s.u * 100);
      setCaudal(enMarcha ? 12 + (Math.random() - 0.5) * 0.4 : 0);
      if (conexion === 'conectado') setHistorial((h) => [...h, { ts: new Date().toISOString(), value: s.t2 }].slice(-300));
    }, PASO_MS);
    return () => window.clearInterval(id);
  }, [activo, marcha, conexion, sp, llenaT1, bajaT2, vaciaT2]);

  return { conexion, conectar, desconectar, marcha, iniciar, detener, sp, cargarSetpoint, n1, n2, t1, t2, salida, caudal, mensaje, chequeos, listo, historial };
}
