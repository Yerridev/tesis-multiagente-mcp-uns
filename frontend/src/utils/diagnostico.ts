import type { Sev } from '../lienzo/tipos';
import type { Diagnostico } from '../components/lienzo/panels/DiagnosticoPanel';

interface Params {
  equipo: string;
  valor: number;
  setpoint: number;
  unit: string;
  tolerancia: number;
  online: boolean;
  historico: boolean;
  momentoTexto: string;
  edad: string;
  cadena: Array<{ de: string; rel: string; a: string }>;
  nota?: string;
}

/**
 * Diagnóstico determinista del módulo (reglas simples y trazables).
 * No usa modelo externo: siempre se puede explicar con los datos que muestra.
 */
export function construirDiagnostico(p: Params): Diagnostico {
  const desviacion = p.valor - p.setpoint;
  const fuera = Math.abs(desviacion) > Math.abs(p.setpoint) * p.tolerancia;
  const haySp = p.setpoint > 0;
  const kpis = [
    { k: 'valor', n: 'Actual', v: p.valor.toFixed(2), u: p.unit },
    { k: 'sp', n: 'Consigna', v: haySp ? p.setpoint.toFixed(2) : '—', u: haySp ? p.unit : undefined },
    { k: 'dev', n: 'Desviación', v: haySp ? desviacion.toFixed(2) : '—', u: haySp ? p.unit : undefined },
    { k: 'edad', n: p.historico ? 'Momento' : 'Antigüedad', v: p.edad },
  ];

  const base = { kpis, cadena: p.cadena, momento: p.momentoTexto };

  if (!p.historico && !p.online) {
    return {
      ...base,
      sev: 'alarma',
      nombre: 'Sin comunicación con el PLC',
      explicacion: `${p.equipo} no reporta lecturas frescas: el último dato recibido ${p.edad}. Los valores mostrados corresponden a la última recepción válida.`,
      recomendacion: 'Verificar alimentación, red y parámetros de comunicación del PLC en campo. Esta interfaz es de solo lectura y no puede restablecer el enlace.',
    };
  }

  if (!(p.setpoint > 0)) {
    /* Sin consigna real publicada: no se evalúa ninguna banda (no se inventan datos) */
    return {
      ...base,
      sev: 'info',
      nombre: 'Sin consigna disponible',
      explicacion: `${p.equipo} reporta ${p.valor.toFixed(2)} ${p.unit} (estado ${p.online ? 'ONLINE' : 'OFFLINE'}), pero no hay una consigna real publicada: no se evalúa la banda de alarma.`,
      recomendacion: 'Lee la consigna del PLC o de su catálogo de señales; esta interfaz no inventa valores ni consignas.',
    };
  }

  if (desviacion > Math.abs(p.setpoint) * p.tolerancia) {
    return {
      ...base,
      sev: 'alarma',
      nombre: 'Sobre la consigna',
      explicacion: `${p.equipo} opera ${Math.abs(desviacion).toFixed(2)} ${p.unit} por encima de la consigna (${p.valor.toFixed(2)} frente a ${p.setpoint.toFixed(2)} ${p.unit}), fuera de la banda de ±${Math.round(p.tolerancia * 100)} %.${p.nota ? ` ${p.nota}` : ''}`,
      recomendacion: 'Revisar en el PLC la acción de control y las condiciones de seguridad que gobiernan este lazo; no cambiar la consigna desde esta interfaz.',
    };
  }

  if (desviacion < -Math.abs(p.setpoint) * p.tolerancia) {
    return {
      ...base,
      sev: 'alarma',
      nombre: 'Por debajo de la consigna',
      explicacion: `${p.equipo} opera ${Math.abs(desviacion).toFixed(2)} ${p.unit} por debajo de la consigna (${p.valor.toFixed(2)} frente a ${p.setpoint.toFixed(2)} ${p.unit}), fuera de la banda de ±${Math.round(p.tolerancia * 100)} %.${p.nota ? ` ${p.nota}` : ''}`,
      recomendacion: 'Revisar en el PLC la acción de control, el elemento de actuación y las condiciones de campo. La interfaz no escribe en el equipo.',
    };
  }

  if (fuera) {
    return {
      ...base,
      sev: 'aviso',
      nombre: 'Desviación de consigna',
      explicacion: `La variable se mantiene dentro de la banda de alarma pero con ${Math.abs(desviacion).toFixed(2)} ${p.unit} de diferencia respecto de la consigna.${p.nota ? ` ${p.nota}` : ''}`,
      recomendacion: 'Observar la tendencia del lazo; si la desviación crece, verificar el sensor y el punto de ajuste en el PLC.',
    };
  }

  return {
    ...base,
    sev: 'normal',
    nombre: 'Operación normal',
    explicacion: `${p.equipo} opera dentro de la banda de ±${Math.round(p.tolerancia * 100)} % de la consigna (${p.valor.toFixed(2)} frente a ${p.setpoint.toFixed(2)} ${p.unit}).${p.nota ? ` ${p.nota}` : ''}`,
    recomendacion: 'Sin acción requerida. La supervisión continúa en modo solo lectura.',
  };
}

export type { Sev };
