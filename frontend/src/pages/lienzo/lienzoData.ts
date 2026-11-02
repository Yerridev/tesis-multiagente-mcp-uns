/**
 * Registro de equipos copiado exactamente de
 * tesis-multiagente-mcp-uns/historiador/mcp_servidor/conocimiento/equipos.json
 * (el lienzo, el agente y la vista de planta se configuran desde aquí).
 */

export interface EquipoLienzo {
  id: string;
  alias: string;
  nombre: string;
  codigo: string;
  proceso: string;
  fabricante: string;
  plc: string;
  ip: string;
  protocolo: string;
  unsBase: string;
  principal: { nombre: string; unidad: string; decimales: number; min: number; max: number };
  secundario: { nombre: string; unidad: string; decimales: number };
  marcha: string;
  diagnosticoRef: string;
  sugerencias: string[];
}

export const ORGANIZACION = {
  campus: 'USS Chiclayo',
  area: 'Laboratorio de Automatización y Simulación de Procesos',
  aula: 'SL01LA07',
  unsRaiz: 'uss/campus/lab-automatizacion/sl01la07',
};

export const EQUIPOS: EquipoLienzo[] = [
  {
    id: 'caudal-mcc09',
    alias: 'caudal',
    nombre: 'Control de caudal',
    codigo: 'MCC-09/002',
    proceso: 'Caudal',
    fabricante: 'Inducontrol',
    plc: 'Siemens S7-200 CPU226 + CP243-1',
    ip: '192.168.114.7',
    protocolo: 'S7 por CP243-1 (enlace 1, TSAP 11.00)',
    unsBase: 'uss/campus/lab-automatizacion/sl01la07/caudal-mcc09',
    principal: { nombre: 'Caudal', unidad: 'L/min', decimales: 1, min: 0, max: 60 },
    secundario: { nombre: 'Setpoint', unidad: 'L/min', decimales: 1 },
    marcha: 'estado/sistema_funcionando',
    diagnosticoRef: 'diagnosticar_lazo',
    sugerencias: [
      '¿El caudal está siguiendo al setpoint? Si no, ¿por qué?',
      '¿Qué equipos influyen sobre el caudal de la línea?',
      '¿Cómo está la banda de alarma del caudal?',
    ],
  },
  {
    id: 'nivel-mcn09',
    alias: 'nivel',
    nombre: 'Control de nivel',
    codigo: 'MCN-09/001',
    proceso: 'Nivel',
    fabricante: 'Inducontrol',
    plc: 'Allen-Bradley MicroLogix 1100 + 1762-IF2OF2',
    ip: '192.168.114.9',
    protocolo: 'EtherNet/IP (PCCC), TCP 44818',
    unsBase: 'uss/campus/lab-automatizacion/sl01la07/nivel-mcn09',
    principal: { nombre: 'Nivel T2', unidad: 'cm', decimales: 1, min: 0, max: 40 },
    secundario: { nombre: 'Frecuencia bomba (est.)', unidad: 'Hz', decimales: 1 },
    marcha: 'estado/bomba_marcha',
    diagnosticoRef: 'diagnosticar_nivel',
    sugerencias: [
      '¿Qué está pasando ahora con el tanque 2?',
      '¿Por qué no funciona el modo REMOTO?',
      '¿Cómo está la bomba y el variador respecto de la consigna?',
    ],
  },
  {
    id: 'presion-mcp09',
    alias: 'presion',
    nombre: 'Control de presión',
    codigo: 'MCP-09/001',
    proceso: 'Presión',
    fabricante: 'Inducontrol',
    plc: 'NI Compact FieldPoint cFP-2200 (LabVIEW RT 8.6) + DI-301, DO-403, AIO-610',
    ip: '192.168.114.8',
    protocolo: 'NI-PSP vía DataSocket (VM Windows 7), solo lectura',
    unsBase: 'uss/campus/lab-automatizacion/sl01la07/presion-mcp09',
    principal: { nombre: 'Presión T2', unidad: 'psi', decimales: 2, min: 0, max: 45 },
    secundario: { nombre: 'Setpoint', unidad: 'psi', decimales: 1 },
    marcha: 'estado/sistema_funcionando',
    diagnosticoRef: 'diagnosticar_presion',
    sugerencias: [
      '¿Por qué la presión no siguió al setpoint en la última prueba?',
      '¿Qué equipos influyen sobre la presión del tanque T2?',
      '¿Hay alarmas de sobre/subpresión activas?',
    ],
  },
  {
    id: 'temp-mct09',
    alias: 'temperatura',
    nombre: 'Control de temperatura',
    codigo: 'MCT-09/001',
    proceso: 'Temperatura',
    fabricante: 'Inducontrol',
    plc: 'Schneider Twido TWDLCAE40DRF + 2x TWDAMM3HT',
    ip: '192.168.114.10',
    protocolo: 'Modbus TCP 502 (unit id 1), solo lectura',
    unsBase: 'uss/campus/lab-automatizacion/sl01la07/temperatura-mct09',
    principal: { nombre: 'Temperatura T2', unidad: '°C', decimales: 1, min: 0, max: 60 },
    secundario: { nombre: 'Setpoint', unidad: '°C', decimales: 1 },
    marcha: 'estado/sistema_funcionando',
    diagnosticoRef: 'diagnosticar_temperatura',
    sugerencias: [
      '¿Qué está pasando ahora con la temperatura del tanque principal?',
      '¿Por qué se calentó el agua el 23-oct con el lazo detenido?',
      'Compara el calentamiento actual con la prueba del SCADA del 24-jul-2010',
    ],
  },
];

export const equipoLienzo = (id: string): EquipoLienzo | undefined => EQUIPOS.find((e) => e.id === id);
