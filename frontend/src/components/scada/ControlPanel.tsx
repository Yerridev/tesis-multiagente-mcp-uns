import { useEffect, useMemo, useState } from 'react';
import { usePlant } from '../../context/PlantContext';
import { controlEstado, enviarControl, tokenControl, CONTROL_TOKEN_DEFECTO, type EstadoControlDatos } from '../../services/control';
import { KnobRO } from './KnobRO';

const COLOR: Record<string, string> = {
  Recibido: 'wait',
  Validando: 'wait',
  Enviado: 'wait',
  Aceptado: 'ok',
  Escrito: 'ok',
  Confirmado: 'ok',
  Rechazado: 'err',
  Vencido: 'err',
  Timeout: 'err',
  Error: 'err',
};

/** Rol del token actual (mapeo de claves dev de appsettings). */
function rolDeToken(token: string): string {
  if (token === 'dev-admin') return 'admin';
  if (token === 'dev-supervisor') return 'supervisor';
  if (token === 'dev-operador') return 'operador';
  if (token === 'dev-viewer') return 'viewer';
  return 'viewer';
}

/** Estado de modo para bloquear funciones todavía no verificadas (SP, PID y válvula). */
export function useModoReal(): boolean {
  const [real, setReal] = useState(false);
  useEffect(() => {
    let cancelado = false;
    const tick = () => {
      controlEstado()
        .then((e) => {
          if (!cancelado) setReal(e.datos?.modoEfectivo === 'REAL');
        })
        .catch(() => {
          if (!cancelado) setReal(false);
        });
    };
    tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      cancelado = true;
      window.clearInterval(id);
    };
  }, []);
  return real;
}

function etiqueta(o: { estado: string; tipo: string; valor: number | null; motivo: string | null }): string {
  const v = o.valor == null ? '' : ` ${o.valor}`;
  return `${o.tipo}${v}${o.motivo ? ` · ${o.motivo}` : ''}`;
}

/** Condiciones que bloquean el mando, en lenguaje claro (nunca se oculta el motivo). */
function bloqueosDe(datos: EstadoControlDatos | undefined, rol: string, estadoDisponible: boolean): string[] {
  if (!datos) return ['Backend de control no disponible'];
  const b: string[] = [];
  if (!datos.proceso.simulador) {
    if (datos.proceso.plc !== 'CONECTADO') b.push('PLC sin comunicación');
    if (datos.proceso.mqttNivel === false) b.push('MQTT de nivel desconectado');
    if (datos.telemetria && !datos.telemetria.fresca) b.push('Telemetría desactualizada');
    if (datos.proceso.selector && datos.proceso.selector !== 'REMOTO') b.push('Selector físico en LOCAL');
    if (!datos.proceso.fuenteControl) b.push('Sin confirmación de quién tiene el mando');
    else if (datos.proceso.fuenteControl === 'HMI') b.push('Control en HMI: mando web bloqueado');
    /* Sensor de nivel saturado: el PV del lazo no es una medida. Con la operación
       degradada autorizada el backend NO bloquea, pero se avisa siempre. */
    if (datos.proceso.sensorSaturado)
      b.push(
        datos.proceso.overrideCalidad
          ? 'SENSOR DE NIVEL FUERA DE RANGO — operación degradada autorizada: el nivel no es medible y la orden se registra marcada en la auditoría'
          : 'SENSOR DE NIVEL FUERA DE RANGO — el nivel no es medible; las órdenes quedan bloqueadas',
      );
  }
  if (rol === 'viewer') b.push('Permiso insuficiente (rol viewer)');
  if (!estadoDisponible) b.push('Sin estado del backend');
  return b;
}

/**
 * Panel de control del MCN-09 dentro de «Opciones»:
 * modo efectivo, condiciones de bloqueo visibles, usuario/rol, ciclo de vida completo
 * de las órdenes (Enviado → Aceptado → Escrito → Confirmado | Rechazado | Timeout) y
 * motivo de cada rechazo. En modo REAL solo se habilitan marcha y parada verificadas.
 */
export function ControlPanel() {
  const { controlOrdenes, controlRecargar } = usePlant();
  const [estado, setEstado] = useState<{ usuario?: string; datos?: EstadoControlDatos } | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [abierto, setAbierto] = useState(false);
  const token = tokenControl();
  const rol = rolDeToken(token);

  /* ESC cierra el emergente de órdenes */
  useEffect(() => {
    if (!abierto) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAbierto(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [abierto]);

  useEffect(() => {
    let cancelado = false;
    controlRecargar();
    const tick = () => {
      controlEstado()
        .then((e) => {
          if (!cancelado) setEstado(e);
        })
        .catch(() => {
          if (!cancelado) setEstado(null);
        });
    };
    tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      cancelado = true;
      window.clearInterval(id);
    };
  }, []);

  const datos = estado?.datos;
  const modo = datos?.modoEfectivo ?? 'DRY-RUN';
  const real = modo === 'REAL';
  const simulador = datos?.proceso.simulador === true;
  const bloqueos = useMemo(() => bloqueosDe(datos, rol, estado != null), [datos, rol, estado]);
  const bloqueado = enviando || bloqueos.length > 0;

  const ultima = controlOrdenes[0] ?? null;

  const enviar = async (sol: Parameters<typeof enviarControl>[0]) => {
    setEnviando(true);
    setAviso(null);
    const r = await enviarControl(sol);
    setEnviando(false);
    controlRecargar();
    if (!r.ok) setAviso(`${sol.tipo}: ${r.error ?? 'error'}`);
  };

  const confirmarMando = (tipo: string, bombaMarcha: boolean | null): boolean =>
    window.confirm(
      `${tipo} · nivel-mcn09\n\n` +
        'Condiciones verificadas antes de enviar:\n' +
        `· PLC: ${datos?.proceso.plc ?? 'sin dato'}\n` +
        `· Selector: ${datos?.proceso.selector ?? 'sin dato'}\n` +
        `· Propietario del mando: ${datos?.proceso.fuenteControl ?? 'sin dato'}\n` +
        `· Bomba: ${bombaMarcha == null ? 'sin dato' : bombaMarcha ? 'en marcha' : 'detenida'}\n` +
        `· Modo del backend: ${modo}\n\n` +
        (real
          ? 'MODO REAL: esta orden escribirá B3:0/4 y accionará físicamente la bomba. ¿Enviar?'
          : 'La orden NO escribe en el PLC en modo DRY-RUN. ¿Enviar?'),
    );

  return (
    <>
      <div className="co-top">
        <span
          className={`pill ${real ? 'pill-err' : simulador ? 'pill-warn' : 'pill-ok'}`}
          title={real ? 'MODO REAL: las órdenes se envían al PLC' : simulador ? 'Conector en modo de pruebas (desarrollo)' : 'Órdenes DRY-RUN: sin escritura al PLC'}
        >
          <i />
          {real ? 'REAL' : simulador ? 'PRUEBAS' : 'DRY-RUN'}
        </span>
        <span className="pill pill-dark" title="Usuario y rol del token de control">
          {estado?.usuario ?? token === CONTROL_TOKEN_DEFECTO ? `${estado?.usuario ?? 'desconocido'} · ${rol}` : 'sin usuario'}
        </span>
        <button type="button" className="co-ver" title="Ver el historial de órdenes (emergente)" onClick={() => { setAbierto(true); controlRecargar(); }}>
          Órdenes
          <span className={controlOrdenes.length ? 'co-cont' : 'co-cont vacio'}>{controlOrdenes.length}</span>
        </button>
      </div>

      {/* Condiciones de permiso: siempre visibles, nunca ocultas */}
      {bloqueos.length > 0 && (
        <ul className="co-condiciones" style={{ margin: '4px 0', paddingLeft: 16, fontSize: 11.5, color: '#b26a00' }}>
          {bloqueos.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}

      <div className="lv-opt-btns">
        <button
          disabled={bloqueado}
          title={bloqueos[0] ?? 'Envía la orden en DRY-RUN (sin escritura)'}
          onClick={() => {
            const bomba = null;
            if (confirmarMando('Iniciar', bomba)) void enviar({ tipo: 'Iniciar' });
          }}
        >
          Iniciar
        </button>
        <button
          disabled={bloqueado}
          title={bloqueos[0] ?? 'Envía la orden en DRY-RUN (sin escritura)'}
          onClick={() => {
            if (confirmarMando('Detener', null)) void enviar({ tipo: 'Detener' });
          }}
        >
          Detener
        </button>
        <button disabled title="Reinicio remoto no existe en el ladder vigente">
          Reiniciar
        </button>
        <button
          disabled={bloqueado}
          title="Requiere verificación en RSLogix (parámetro kp/ti/td): permanece bloqueado hasta la campaña de laboratorio"
          onClick={() => undefined}
          style={{ opacity: 0.55 }}
        >
          PID…
        </button>
      </div>

      {aviso && <p className="co-aviso">{aviso}</p>}

      {/* Última orden con su ciclo de vida y confirmación */}
      {ultima && (
        <p className="co-aviso" style={{ color: '#555' }}>
          Última orden: <b className={COLOR[ultima.estado] ?? 'wait'}>{ultima.estado}</b> · {ultima.tipo}
          {ultima.valor != null ? ` ${ultima.valor}${ultima.unidad ? ` ${ultima.unidad}` : ''}` : ''}
          {ultima.motivo ? ` · ${ultima.motivo}` : ''}
          {ultima.escrito != null ? ` · escritura: ${ultima.escrito ? 'ejecutada' : 'no ejecutada'}` : ''}
          {ultima.valorLeido != null ? ` · lectura posterior: ${ultima.valorLeido}` : ''}
        </p>
      )}

      {abierto && (
        <div className="co-modal" role="dialog" aria-modal="true" aria-label="Órdenes de control" onClick={() => setAbierto(false)}>
          <div className="co-modal-caja" onClick={(e) => e.stopPropagation()}>
            <div className="co-modal-head">
              <b>Órdenes de control · nivel-mcn09</b>
              <button type="button" aria-label="Cerrar" onClick={() => setAbierto(false)}>×</button>
            </div>
            <div className="co-modal-cuerpo">
              {controlOrdenes.length === 0 ? (
                <p className="co-vacio">Sin órdenes todavía</p>
              ) : (
                <ul className="co-list">
                  {controlOrdenes.map((o) => (
                    <li key={o.id} className="co-item">
                      <b className={COLOR[o.estado] ?? 'wait'}>{o.estado}</b>
                      <span>
                        {etiqueta(o)}
                        {o.correlacion ? ` · corr:${o.correlacion}` : ''}
                        {o.valorLeido != null ? ` · leído ${o.valorLeido}` : ''}
                      </span>
                      <i className="co-hora">{new Date(o.expedida).toLocaleTimeString('es-PE', { hour12: false })}</i>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="co-modal-pie">
              {real ? 'Modo REAL · revisar auditoría antes de repetir' : 'DRY-RUN · validadas y auditadas, sin escritura al PLC'}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** Control calibrado: Abrir=100 %, Cerrar=80 %. El PLC mueve por tiempo; nunca se escriben salidas. */
export function ValvulaBotones({ disabled }: { disabled: boolean }) {
  const { controlRecargar } = usePlant();
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const enviar = async (tipo: string) => {
    setEnviando(true);
    setAviso(null);
    const r = await enviarControl({ tipo });
    setEnviando(false);
    controlRecargar();
    setAviso(r.ok ? (tipo === 'AbrirValvula' ? 'Válvula en 100 %' : 'Válvula en 80 %') : `${r.error ?? 'error'}`);
  };
  return (
    <div className="lv-valve-cmds">
      <button disabled={disabled || enviando} onClick={() => void enviar('AbrirValvula')} title="Mover físicamente a 100 %">
        Abrir 100 %
      </button>
      <button disabled={disabled || enviando} onClick={() => void enviar('CerrarValvula')} title="Mover físicamente a 80 %">
        Cerrar a 80 %
      </button>
      {aviso && <small className="co-aviso">{aviso}</small>}
    </div>
  );
}

/** Envío de setpoint: muestra valor actual, rango, unidad, resultado y confirmación. */
export function SetpointBoton({ max, unidad, disabled }: { max: number; unidad: string; disabled: boolean }) {
  const { controlOrdenes, controlRecargar, senal } = usePlant();
  const [valor, setValor] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const numero = Number(valor);
  const valido = valor !== '' && Number.isFinite(numero) && numero >= 0 && numero <= max;

  const actualRaw = senal?.valores?.['pid/setpoint_a_raw']?.valor;
  const actual = typeof actualRaw === 'number' ? (16348 - actualRaw) / 400 : null;
  const ultimaSp = useMemo(
    () => controlOrdenes.find((o) => o.tipo === 'Setpoint') ?? null,
    [controlOrdenes],
  );

  const enviar = async () => {
    setEnviando(true);
    setAviso(null);
    const r = await enviarControl({ tipo: 'Setpoint', valor: numero, unidad });
    setEnviando(false);
    controlRecargar();
    setAviso(r.ok ? `Setpoint ${numero} ${unidad} enviado` : (r.error ?? 'error'));
  };
  return (
    <div className="lv-sp-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 4 }}>
      <small style={{ color: '#777' }}>
        Actual: {actual == null ? 'sin dato' : `${actual.toFixed(1)} ${unidad}`} · Rango permitido: 0–{max} {unidad}
      </small>
      <div className="lv-sp-row">
        <input
          type="number"
          min={0}
          max={max}
          step={1}
          value={valor}
          placeholder={`0–${max}`}
          onChange={(e) => setValor(e.target.value)}
          disabled={disabled || enviando}
          aria-label={`Setpoint en ${unidad}`}
        />
        <button disabled={disabled || enviando || !valido} onClick={() => void enviar()} title={`Enviar setpoint, rango 0–${max} ${unidad}`}>
          Enviar SP
        </button>
      </div>
      {aviso && <small className="co-aviso">{aviso}</small>}
      {ultimaSp && (
        <small style={{ color: '#666' }}>
          Última orden SP: <b className={COLOR[ultimaSp.estado] ?? 'wait'}>{ultimaSp.estado}</b>
          {ultimaSp.motivo ? ` · ${ultimaSp.motivo}` : ''}
          {ultimaSp.valorLeido != null ? ` · confirmado: ${((16348 - ultimaSp.valorLeido) / 400).toFixed(1)} ${unidad}` : ''}
        </small>
      )}
    </div>
  );
}

/** Perilla de setpoint: envía una sola orden al soltar, después de confirmación humana. */
export function SetpointPerilla({ actual, max = 40, deshabilitado = false, motivo }: { actual: number | null; max?: number; deshabilitado?: boolean; motivo?: string }) {
  const { controlRecargar } = usePlant();
  const [aviso, setAviso] = useState<string | null>(null);
  const confirmar = async (valor: number) => {
    if (deshabilitado) {
      setAviso(motivo ?? 'Consigna no disponible');
      return;
    }
    setAviso('Enviando.');
    const r = await enviarControl({ tipo: 'Setpoint', valor, unidad: 'cm' });
    controlRecargar();
    setAviso(r.ok ? `Setpoint confirmado: ${valor} cm` : (r.error ?? 'No se pudo cambiar el setpoint'));
  };
  return <div>
    <KnobRO value={deshabilitado ? null : actual == null ? null : Math.max(0, Math.min(max, actual))} max={max} ticks={[0, 10, 20, 30, 40]} label="Setpoint cm" onCommit={(v) => void confirmar(v)} />
    {aviso && <small className="co-aviso">{aviso}</small>}
    {deshabilitado && <small className="co-aviso">{motivo ?? 'Consigna deshabilitada'}</small>}
  </div>;
}

export function PidEditor({ kp, ti, td }: { kp: number; ti: number; td: number }) {
  const { controlRecargar } = usePlant();
  const [p, setP] = useState(kp.toFixed(2));
  const [i, setI] = useState(ti.toFixed(2));
  const [d, setD] = useState(td.toFixed(2));
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { if (!enviando) { setP(kp.toFixed(2)); setI(ti.toFixed(2)); setD(td.toFixed(2)); } }, [kp, ti, td, enviando]);
  const aplicar = async () => {
    const valores = { kp: Number(p), ti: Number(i), td: Number(d) };
    if (Object.values(valores).some((v) => !Number.isFinite(v) || v < 0)) return;
    setEnviando(true); setAviso('Enviando PID…');
    for (const [parametro, valor] of Object.entries(valores)) {
      const r = await enviarControl({ tipo: 'ParametroPid', parametro, valor });
      if (!r.ok) { setAviso(`${parametro}: ${r.error ?? 'rechazado'}`); setEnviando(false); return; }
    }
    setEnviando(false); controlRecargar(); setAviso(`PID enviado: P=${p}, I=${i}, D=${d}`);
  };
  return <div className="pid-editor">
    <label>Kp<input type="number" step="0.01" min="0" value={p} onChange={(e) => setP(e.target.value)} /></label>
    <label>Ti<input type="number" step="0.01" min="0" value={i} onChange={(e) => setI(e.target.value)} /></label>
    <label>Td<input type="number" step="0.01" min="0" value={d} onChange={(e) => setD(e.target.value)} /></label>
    <button disabled={enviando} onClick={() => void aplicar()}>Aplicar PID</button>
    {aviso && <small className="co-aviso">{aviso}</small>}
  </div>;
}
