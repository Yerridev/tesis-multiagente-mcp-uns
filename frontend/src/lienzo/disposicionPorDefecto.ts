/**
 * Disposición POR DEFECTO de los 4 lienzos (la que dejó el usuario, copiada de registros/lienzos el 18-nov-2026).
 * Se usa cuando el navegador y el servidor no tienen una guardada: así los lienzos siempre salen ordenados.
 */
export const DISPOSICION_POR_DEFECTO: Record<string, { posiciones: Record<string, { x: number; y: number }>; lados: Record<string, { s?: string; t?: string }> }> = {
 "caudal-mcc09": {
  "posiciones": {
   "tanque": {
    "x": -6,
    "y": 519
   },
   "sensor_nivel": {
    "x": -8,
    "y": 341
   },
   "variador": {
    "x": 320,
    "y": 164
   },
   "plc": {
    "x": 1047,
    "y": 255
   },
   "potenciometro": {
    "x": -3,
    "y": -7
   },
   "selector": {
    "x": 320,
    "y": -9
   },
   "panel:agente": {
    "x": 1331,
    "y": 493
   },
   "panel:diagnostico": {
    "x": 1331,
    "y": 2
   },
   "caudalimetro": {
    "x": 1049,
    "y": 520
   },
   "linea": {
    "x": 678,
    "y": 435
   },
   "pid": {
    "x": 675,
    "y": 227
   },
   "valvula": {
    "x": 678,
    "y": 688
   },
   "pc_scada": {
    "x": 673,
    "y": -7
   },
   "sensor_nivel_alto": {
    "x": -7,
    "y": 712
   },
   "hmi": {
    "x": 1048,
    "y": -10
   }
  },
  "lados": {}
 },
 "nivel-mcn09": {
  "posiciones": {
   "valvula": {
    "x": 960,
    "y": 735
   },
   "bomba": {
    "x": 266,
    "y": 370
   },
   "tanque_t2": {
    "x": 620,
    "y": 616
   },
   "interruptor_nivel_t1": {
    "x": 361,
    "y": 653
   },
   "pid": {
    "x": 610,
    "y": 233
   },
   "pulsadores": {
    "x": 103,
    "y": 655
   },
   "tanque_t1": {
    "x": -66,
    "y": 463
   },
   "variador": {
    "x": -61,
    "y": 240
   },
   "potenciometro": {
    "x": -61,
    "y": 2
   },
   "selector": {
    "x": 612,
    "y": 0
   },
   "plc": {
    "x": 966,
    "y": 238
   }
  },
  "lados": {
   "bomba|impulsa|tanque_t2": {
    "s": "s-right",
    "t": "t-top"
   },
   "interruptor_nivel_t1|protege|bomba": {
    "t": "t-bottom",
    "s": "s-top"
   },
   "tanque_t2|descarga_en|tanque_t1": {
    "t": "t-bottom",
    "s": "s-bottom"
   }
  }
 },
 "presion-mcp09": {
  "posiciones": {
   "tanque_t1": {
    "x": 325,
    "y": 742
   },
   "interruptores_nivel_t1": {
    "x": -10,
    "y": 724
   },
   "valvula": {
    "x": 1027,
    "y": 586
   },
   "transmisor": {
    "x": 820,
    "y": 368
   },
   "variador": {
    "x": -3,
    "y": 355
   },
   "pid": {
    "x": 448,
    "y": 246
   },
   "pac": {
    "x": -7,
    "y": -8
   },
   "selector": {
    "x": 449,
    "y": -4
   },
   "tanque_t2": {
    "x": 651,
    "y": 661
   },
   "presostato": {
    "x": 1027,
    "y": 769
   },
   "bomba": {
    "x": 325,
    "y": 510
   },
   "pulsadores": {
    "x": -11,
    "y": 559
   },
   "potenciometro_variador": {
    "x": -6,
    "y": 123
   },
   "supervisor": {
    "x": 1022,
    "y": -4
   }
  },
  "lados": {}
 },
 "temp-mct09": {
  "posiciones": {
   "interruptores_nivel": {
    "x": 0,
    "y": 2
   },
   "selector": {
    "x": 509,
    "y": 0
   },
   "supervisor": {
    "x": 942,
    "y": 6
   },
   "variador": {
    "x": 1303,
    "y": 15
   },
   "pid": {
    "x": 512,
    "y": 179
   },
   "sensor_principal": {
    "x": 2,
    "y": 274
   },
   "rele_ssr": {
    "x": 937,
    "y": 281
   },
   "termomagnetica": {
    "x": 1288,
    "y": 296
   },
   "plc": {
    "x": 281,
    "y": 392
   },
   "enfriador": {
    "x": 635,
    "y": 479
   },
   "pulsadores_enfriador": {
    "x": 956,
    "y": 489
   },
   "sensor_enfriador": {
    "x": 217,
    "y": 581
   },
   "tanque_enfriador": {
    "x": 637,
    "y": 706
   },
   "resistencia": {
    "x": 984,
    "y": 695
   },
   "bomba": {
    "x": 1292,
    "y": 715
   },
   "tanque_principal": {
    "x": 4,
    "y": 761
   }
  },
  "lados": {
   "sensor_principal|mide|tanque_principal": {
    "s": "s-left",
    "t": "t-left"
   },
   "resistencia|calienta|tanque_principal": {
    "s": "s-bottom",
    "t": "t-bottom"
   },
   "tanque_principal|alimenta|bomba": {
    "s": "s-bottom",
    "t": "t-bottom"
   },
   "bomba|recircula|tanque_enfriador": {
    "s": "s-bottom",
    "t": "t-right"
   },
   "rele_ssr|energiza|resistencia": {
    "s": "s-bottom",
    "t": "t-right"
   },
   "variador|acciona|bomba": {
    "s": "s-right",
    "t": "t-right"
   },
   "plc|controla|enfriador": {
    "s": "s-bottom",
    "t": "t-left"
   },
   "plc|ejecuta|pid": {
    "s": "s-right",
    "t": "t-bottom"
   },
   "interruptores_nivel|bloquea|pid": {
    "s": "s-right",
    "t": "t-left"
   },
   "pid|lee|sensor_principal": {
    "s": "s-left",
    "t": "t-right"
   },
   "supervisor|fija_setpoint|pid": {
    "s": "s-left",
    "t": "t-right"
   },
   "pid|controla|rele_ssr": {
    "s": "s-right",
    "t": "t-left"
   },
   "supervisor|fija_velocidad|variador": {
    "s": "s-right",
    "t": "t-left"
   },
   "termomagnetica|alimenta|rele_ssr": {
    "s": "s-left",
    "t": "t-right"
   },
   "pulsadores_enfriador|habilita|enfriador": {
    "s": "s-left",
    "t": "t-right"
   },
   "selector|habilita|pid": {
    "s": "s-bottom",
    "t": "t-top"
   },
   "enfriador|enfria|tanque_enfriador": {
    "s": "s-bottom",
    "t": "t-top"
   },
   "sensor_enfriador|mide|tanque_enfriador": {
    "s": "s-right",
    "t": "t-left"
   },
   "tanque_enfriador|descarga_en|tanque_principal": {
    "s": "s-left",
    "t": "t-right"
   }
  }
 }
};
