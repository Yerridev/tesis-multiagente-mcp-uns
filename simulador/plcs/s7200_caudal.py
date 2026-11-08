"""PLC virtual Siemens S7-200 (CPU226 + CP243-1) del modulo de caudal MCC-09.

Expone las areas S7 con python-snap7 (servidor S7 puro Python), con el MISMO mapa que usa
conector_edge_s7200.py, que funciona sin cambios contra el simulador:
  V (DB1): VD159 PV PID (0..1)  VD163 SP PID (0..1)  VD167 salida PID (0..1)  VD171 Kc  VD175 Ts (s)
           VD179 Ti (min)  VD183 Td (min)  VD187 Mx  VD400 SP remoto (L/min)  VD408 SP HMI (L/min)
           VW8 consigna del variador (0..32000)  VD100/VD108/VD116 Kc/Ti/Td escritos por la PC
  M: M0.2 arranque remoto  M0.3 mando HMI(1)/PC(0)  M0.6 SP desde HMI  MW2 potenciometro (local)
     MW3 caudalimetro crudo (AIW0, remoto)  MW25 apertura de la valvula (0..32000)
  I: I0.0 selector REMOTO  I0.1 selector LOCAL  I0.2 hay agua en T1
  Q: Q0.0 nivel alto  Q0.1 nivel bajo (= NOT I0.2)  Q0.2 sistema funcionando

El PID sigue el algoritmo del S7-200 (PID de posicion normalizado con Kc, Ts, Ti y Td en minutos
y bias Mx). La logica de escalera es una reconstruccion; sirve para probar SCADA, conectores y agentes.
"""
from __future__ import annotations

from dataclasses import dataclass

from snap7.util import get_bool, get_int, get_real, set_bool, set_int, set_real

from ..plantas.caudal import PlantaCaudal

FONDO_ESCALA = 140.0      # L/min: el programa normaliza VD400 / 140
CUENTAS_AQ = 32000        # salidas analogicas del S7-200: 0..32000 = 0..100 %


def q_a_aiw(q: float) -> int:
    """Inversa de la calibracion del caudalimetro: q = 0.005498*AIW0 - 34.896."""
    return max(0, min(32767, round((q + 34.896) / 0.005498)))


@dataclass
class Entradas:
    selector: str = "remoto"        # remoto | local | off
    mando: str = "pc"               # pc | hmi (M0.3)
    agua_t1: bool = True            # I0.2
    nivel_alto: bool = False        # Q0.0
    arranque_local: bool = False    # pulsador de arranque del tablero (modo LOCAL)
    potenciometro_pct: float = 50.0  # perilla del tablero (modo LOCAL)


class S7200Caudal:
    def __init__(self, planta: PlantaCaudal):
        self.planta = planta
        self.V = bytearray(1024)
        self.M = bytearray(64)
        self.I = bytearray(8)
        self.Q = bytearray(8)
        self.ent = Entradas()
        self._t_pid = 0.0
        self._pv_prev: float | None = None
        V = self.V
        set_real(V, 171, 1.0); set_real(V, 175, 0.2); set_real(V, 179, 0.05); set_real(V, 183, 0.0)
        set_real(V, 100, 1.0); set_real(V, 108, 0.05); set_real(V, 116, 0.0)
        set_real(V, 400, 20.0); set_real(V, 408, 0.0)
        set_int(self.M, 25, CUENTAS_AQ)   # valvula abierta al iniciar (supuesto)

    def scan(self, dt: float):
        V, M, I, Q, e = self.V, self.M, self.I, self.Q, self.ent
        # Entradas fisicas
        set_bool(I, 0, 0, e.selector == "remoto")
        set_bool(I, 0, 1, e.selector == "local")
        set_bool(I, 0, 2, e.agua_t1)
        set_bool(M, 0, 3, e.mando == "hmi")
        remoto, local, agua = get_bool(I, 0, 0), get_bool(I, 0, 1), get_bool(I, 0, 2)
        self.planta.e.agua_ok = agua

        # Niveles y marcha
        set_bool(Q, 0, 0, e.nivel_alto)
        set_bool(Q, 0, 1, not agua)
        if not agua:
            set_bool(M, 0, 2, False)        # nivel bajo borra la orden de arranque
        marcha = agua and ((remoto and get_bool(M, 0, 2)) or (local and e.arranque_local))
        set_bool(Q, 0, 2, marcha)

        # Parametros PID escritos por la PC (VD100/108/116) -> tabla del lazo
        if get_real(V, 100) > 0:
            set_real(V, 171, get_real(V, 100))
            set_real(V, 179, get_real(V, 108))
            set_real(V, 183, get_real(V, 116))

        # Medicion
        q = self.planta.lectura()
        set_real(V, 159, min(1.0, q / FONDO_ESCALA))
        if remoto:
            set_int(M, 3, q_a_aiw(q))
        else:
            set_int(M, 2, round(e.potenciometro_pct * CUENTAS_AQ / 100))

        # Setpoint
        sp_lpm = get_real(V, 408) if get_bool(M, 0, 6) else get_real(V, 400)
        set_real(V, 163, max(0.0, min(1.0, sp_lpm / FONDO_ESCALA)))

        # PID S7-200 (solo en REMOTO con el sistema en marcha)
        if marcha and remoto:
            self._t_pid += dt
            ts = max(0.05, get_real(V, 175))
            if self._t_pid >= ts:
                self._t_pid = 0.0
                pv, sp = get_real(V, 159), get_real(V, 163)
                kc, ti, td = get_real(V, 171), get_real(V, 179) * 60, get_real(V, 183) * 60
                mx = get_real(V, 187)
                err = sp - pv
                mp = kc * err
                mi = (kc * ts / ti * err + mx) if ti > 0 else mx
                mi = max(0.0, min(1.0, mi))
                md = kc * td / ts * ((self._pv_prev if self._pv_prev is not None else pv) - pv)
                self._pv_prev = pv
                mn = max(0.0, min(1.0, mp + mi + md))
                set_real(V, 167, mn)
                set_real(V, 187, mi)
            set_int(V, 8, round(get_real(V, 167) * CUENTAS_AQ))
        else:
            self._t_pid, self._pv_prev = 0.0, None
            set_real(V, 167, 0.0)
            set_real(V, 187, 0.0)
            set_int(V, 8, round(e.potenciometro_pct * CUENTAS_AQ / 100) if (marcha and local) else 0)

        # Valvula: en LOCAL el programa la fuerza al 100 %
        if local:
            set_int(M, 25, CUENTAS_AQ)

        # Fisica
        self.planta.paso(dt, bomba_on=marcha, velocidad_pct=get_int(V, 8) / 320.0,
                         valvula_pct=get_int(M, 25) / 320.0)

    def resumen(self) -> str:
        V, M = self.V, self.M
        return (f"Q={self.planta.e.caudal:6.2f} L/min  SP={get_real(V, 400):5.1f}  "
                f"PID={get_real(V, 167) * 100:5.1f} %  variador={get_int(V, 8) / 320:5.1f} %  "
                f"valvula={get_int(M, 25) / 320:5.1f} %  marcha={'ON ' if get_bool(self.Q, 0, 2) else 'OFF'}  "
                f"selector={self.ent.selector}")
