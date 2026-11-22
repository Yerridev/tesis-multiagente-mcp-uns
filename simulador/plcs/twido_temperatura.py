"""PLC virtual Schneider Twido del modulo de temperatura MCT-09.

Reproduce el MISMO mapa de memoria que leen y escriben los conectores reales
(conector_edge_twido.py y conector_control_temperatura.py), por eso estos funcionan
sin cambios; solo se les pasa la IP del simulador con --plc.

Memoria (base 0, igual que el Twido):
  %MW0  temperatura principal (cuentas 0..4095 = 0..100 C)   %MW1  temperatura enfriador
  %MW10 consigna del variador (0..4095 = 0..10 V)
  %MW100 SP (cuentas de temperatura)  %MW101 Kp  %MW102 Ti  %MW103 Td  %MW110 salida PID (0..10000)
  %M0/%M1 selector PC/HMI  %M2/%M3 pulsadores enfriador  %M4..%M7 interruptores de nivel
  %M12 sistema funcionando  %M13 bomba  %M14 resistencia (PWM)  %M15..%M18 alarmas de nivel
  %M19 enfriador  %M20/%M21 fallas de nivel  %M30..%M33 inicio/lazo PC y HMI
  %M40..%M43 habilitacion del enfriador  %M44 T > SP sostenido (temporizador %TM0)

La logica de escalera es una reconstruccion a partir del respaldo Twido1.xtwd (2009) y del
SCADA LabVIEW; el PID usa la forma posicional con anti-windup. No pretende ser identico al
bloque PID del Twido: sirve para probar el SCADA, los conectores y los agentes MCP.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..plantas.temperatura import PlantaTemperatura
from .modbus_tcp import Memoria

CUENTAS = 4095
PERIODO_PWM = 2.0        # s, ciclo del rele de estado solido
TM0 = 10.0               # s que T debe superar el SP para pedir enfriamiento
PERIODO_PID = 1.0      # s, periodo de muestreo del PID (Twido: parametro del bloque PID)
TAU_FILTRO = 2.0       # s, filtro de la medicion para la accion derivativa
VARIADOR_MARCHA = 2458   # cuentas (~60 %) que el programa manda al variador con la bomba en marcha (supuesto)


def a_cuentas(c: float) -> int:
    return max(0, min(CUENTAS, round(c * CUENTAS / 100.0)))


@dataclass
class Entradas:
    """Entradas fisicas del tablero (las cambian los escenarios)."""
    selector: str = "pc"            # pc | hmi | off
    nivel_alto_principal: bool = False
    nivel_bajo_principal_ok: bool = True
    nivel_alto_enfriador: bool = False
    nivel_bajo_enfriador_ok: bool = True


class TwidoTemperatura:
    def __init__(self, planta: PlantaTemperatura, mem: Memoria | None = None):
        self.planta = planta
        self.mem = mem or Memoria(n_coils=64, n_regs=128)
        self.ent = Entradas()
        self._integral = 0.0
        self._pv_filtrada = None
        self._pv_previa = None
        self._t_pid = 0.0
        self._salida = 0.0
        self._t_pwm = 0.0
        self._t_sobre_sp = 0.0
        self._enf_habilitado = False
        r = self.mem.regs
        r[101], r[102], r[103] = 5000, 10, 10   # parametros PID de fabrica
        r[100] = 0                              # el SP se pierde al apagar el PLC real
        self.mem.coils[3] = True                # pulsador DESHABILITAR ENFRIADOR es NC

    # ---------- ciclo de scan ----------
    def scan(self, dt: float):
        c, r, e = self.mem.coils, self.mem.regs, self.ent

        # Entradas fisicas
        c[0] = e.selector == "pc"
        c[1] = e.selector == "hmi"
        c[4] = e.nivel_alto_principal
        c[5] = e.nivel_bajo_principal_ok
        c[6] = e.nivel_alto_enfriador
        c[7] = e.nivel_bajo_enfriador_ok
        self.planta.e.agua_principal_ok = e.nivel_bajo_principal_ok

        # Fallas y alarmas de nivel
        c[20] = c[4] or not c[5]
        c[21] = c[6] or not c[7]
        c[15], c[16], c[17], c[18] = c[4], not c[5], c[6], not c[7]
        falla = c[20] or c[21]
        if falla:                       # una falla de nivel detiene el lazo y borra las ordenes
            c[30] = c[32] = False

        # Marcha del lazo
        c[31] = c[0] and not c[1] and c[30] and not falla
        c[33] = c[1] and not c[0] and c[32] and not falla
        c[12] = c[31] or c[33]
        c[13] = c[12]
        r[10] = VARIADOR_MARCHA if c[13] else 0

        # Medicion (transmisores 4-20 mA -> 0..4095)
        r[0] = a_cuentas(self.planta.lectura_principal())
        r[1] = a_cuentas(self.planta.lectura_enfriador())

        # PID 0: muestreo cada PERIODO_PID; derivada sobre la medicion filtrada (evita amplificar ruido)
        pv_c = r[0] * 100.0 / CUENTAS
        if self._pv_filtrada is None:
            self._pv_filtrada = pv_c
        self._pv_filtrada += (pv_c - self._pv_filtrada) * min(1.0, dt / TAU_FILTRO)
        if c[12]:
            self._t_pid += dt
            if self._t_pid >= PERIODO_PID:
                h, self._t_pid = self._t_pid, 0.0
                sp = r[100] * 100.0 / CUENTAS
                err = sp - self._pv_filtrada                # % del rango (0..100 C = 0..100 %)
                kp = r[101] / 100.0
                ti = r[102] / 10.0                          # decimas de segundo -> s
                td = r[103] / 10.0
                dpv = 0.0 if self._pv_previa is None else (self._pv_filtrada - self._pv_previa) / h
                self._pv_previa = self._pv_filtrada
                if ti > 0 and kp > 0:
                    self._integral += err * h / ti
                    lim = 100.0 / kp                        # anti-windup: kp*integral en 0..100
                    self._integral = max(-lim, min(lim, self._integral))
                self._salida = max(0.0, min(100.0, kp * (err + self._integral - td * dpv)))
        else:
            self._salida, self._integral, self._pv_previa, self._t_pid = 0.0, 0.0, None, 0.0
        salida = self._salida
        r[110] = round(salida * 100)

        # PWM de la resistencia
        self._t_pwm = (self._t_pwm + dt) % PERIODO_PWM
        c[14] = c[12] and self._t_pwm < PERIODO_PWM * salida / 100.0

        # Enfriador: habilitacion (pulsadores HMI o mandos PC) y temporizador T > SP
        if c[2] or c[41]:
            self._enf_habilitado = True
        if not c[3] or c[42]:
            self._enf_habilitado = False
        c[40] = self._enf_habilitado and c[1]
        c[43] = c[0] and not falla
        if c[12] and r[0] > r[100]:
            self._t_sobre_sp += dt
        else:
            self._t_sobre_sp = 0.0
        c[44] = self._t_sobre_sp >= TM0
        c[19] = c[12] and c[44] and (self._enf_habilitado or c[43])

        # Fisica
        bomba_pct = r[10] * 100.0 / CUENTAS
        self.planta.paso(dt, resistencia_on=c[14], bomba_pct=bomba_pct, enfriador_on=c[19])

    def resumen(self) -> str:
        c, r = self.mem.coils, self.mem.regs
        sp = r[100] * 100 / CUENTAS
        return (f"T={self.planta.e.t_principal:6.2f} C  Tenf={self.planta.e.t_enfriador:6.2f} C  "
                f"SP={sp:5.1f} C  PID={r[110] / 100:5.1f} %  lazo={'ON ' if c[12] else 'OFF'}  "
                f"enfriador={'ON' if c[19] else 'off'}  selector={self.ent.selector}")
