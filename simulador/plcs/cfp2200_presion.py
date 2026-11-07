"""Controlador virtual NI Compact FieldPoint cFP-2200 (programa LabVIEW RT) del modulo de presion MCP-09.

Expone las MISMAS variables compartidas que leen/escriben conector_edge_cfp2200.py y
conector_control_presion.py (psp://<cFP>/DATOS_PAC/..., pid/..., FP/3AIO/00).
Como NI-PSP es propietario, el simulador las sirve por un protocolo JSON simple (plcs/psp_sim.py)
y los conectores se ejecutan con el shim simulador/psp_shim en PYTHONPATH (sin cambiar su codigo).

Logica RT (reconstruccion):
  REMOTO (SEL_AUTO) + PC_TPM: flanco de INICIO_PC arranca; SALIR_PC detiene. PID -> VARIADOR (0-10 V),
  VAL_PROPOR = pid/valvula_pc.  LOCAL (SEL_MANUAL): ARRANQUE_MANUAL arranca, PARADA_MANUAL (NC) detiene,
  VARIADOR = POTENCIOMETRO.  SWITCH_NB = False (T1 sin agua) detiene la bomba.
  PID: Kp_PC, Ti_PC y Td_PC en minutos (estilo NI PID), error en psi, salida 0-10 V.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..plantas.presion import PSI_FONDO_ESCALA, PlantaPresion

PERIODO_PID = 0.1


@dataclass
class Entradas:
    selector: str = "remoto"     # remoto | local | off
    potenciometro_v: float = 5.0
    arranque: bool = False
    parada_ok: bool = True       # NC
    nivel_alto_t1: bool = False


class CFP2200Presion:
    def __init__(self, planta: PlantaPresion):
        self.planta = planta
        self.ent = Entradas()
        self.vars: dict[str, object] = {
            "DATOS_PAC/PC_TPM": True,
            "DATOS_PAC/INICIO_PC": False, "DATOS_PAC/SALIR_PC": False,
            "pid/setpoint_pc": 10.0, "pid/SETPOINT_TPM": 10.0,
            "pid/Kp_PC": 3.0, "pid/Ti_PC": 0.05, "pid/Td_PC": 0.0,
            "pid/valvula_pc": 3.0, "pid/salida_pid": 0.0,
        }
        self.escribibles = {"DATOS_PAC/INICIO_PC", "DATOS_PAC/SALIR_PC", "DATOS_PAC/PC_TPM",
                            "pid/setpoint_pc", "pid/SETPOINT_TPM", "pid/Kp_PC", "pid/Ti_PC", "pid/Td_PC",
                            "pid/valvula_pc"}
        self._inicio_prev = False
        self._marcha_pc = self._marcha_local = False
        self._integral = 0.0
        self._t_pid = 0.0
        self._pv_prev = None
        self.scan(0.0)

    def escribir(self, url: str, valor) -> bool:
        if url not in self.escribibles:
            return False
        self.vars[url] = valor
        return True

    def scan(self, dt: float):
        v, e, pl = self.vars, self.ent, self.planta
        remoto, local = e.selector == "remoto", e.selector == "local"
        agua = pl.e.agua_t1
        v.update({"DATOS_PAC/SEL_AUTO": remoto, "DATOS_PAC/SEL_MANUAL": local,
                  "DATOS_PAC/ARRANQUE_MANUAL": e.arranque, "DATOS_PAC/PARADA_MANUAL": e.parada_ok,
                  "DATOS_PAC/SWITCH_NB": agua, "DATOS_PAC/SWITCH_NA": e.nivel_alto_t1,
                  "DATOS_PAC/POTENCIOMETRO": float(e.potenciometro_v)})
        pc = bool(v["DATOS_PAC/PC_TPM"])
        inicio = bool(v["DATOS_PAC/INICIO_PC"])
        if inicio and not self._inicio_prev and remoto and pc and agua and not v["DATOS_PAC/SALIR_PC"]:
            self._marcha_pc = True
        self._inicio_prev = inicio
        if v["DATOS_PAC/SALIR_PC"] or not remoto or not pc or not agua:
            self._marcha_pc = False
        if local and e.arranque and agua and e.parada_ok:
            self._marcha_local = True
        if not local or not e.parada_ok or not agua:
            self._marcha_local = False
        marcha = self._marcha_pc or self._marcha_local

        corriente = pl.corriente_a()
        psi = max(0.0, (corriente * 1000 - 4) / 16 * PSI_FONDO_ESCALA)
        if self._marcha_pc:
            self._t_pid += dt
            if self._t_pid >= PERIODO_PID:
                h, self._t_pid = self._t_pid, 0.0
                sp = float(v["pid/setpoint_pc"])
                kp, ti, td = float(v["pid/Kp_PC"]), float(v["pid/Ti_PC"]) * 60, float(v["pid/Td_PC"]) * 60
                err = sp - psi
                dpv = 0.0 if self._pv_prev is None else (psi - self._pv_prev) / h
                self._pv_prev = psi
                if ti > 0 and kp > 0:
                    self._integral += kp * err * h / ti
                    self._integral = max(0.0, min(10.0, self._integral))
                v["pid/salida_pid"] = max(0.0, min(10.0, kp * err + self._integral - kp * td * dpv))
        else:
            self._integral, self._pv_prev, self._t_pid = 0.0, None, 0.0
            v["pid/salida_pid"] = 0.0
        variador = v["pid/salida_pid"] if self._marcha_pc else (e.potenciometro_v if self._marcha_local else 0.0)
        valvula = float(v["pid/valvula_pc"]) if remoto else 10.0
        v.update({"DATOS_PAC/TRANS_PRESION": corriente, "FP/3AIO/00": corriente,
                  "DATOS_PAC/VARIADOR": float(variador), "DATOS_PAC/VAL_PROPOR": valvula,
                  "DATOS_PAC/LED_SIST_FUN": marcha, "DATOS_PAC/ACT_VARIADOR": marcha,
                  "DATOS_PAC/LED_NA": e.nivel_alto_t1, "DATOS_PAC/LED_NB": not agua,
                  "DATOS_PAC/PRESOS": pl.e.presion > 60.0})
        pl.paso(dt, variador, valvula)

    def resumen(self) -> str:
        v = self.vars
        return (f"P={self.planta.e.presion:5.1f} psi  SP={float(v['pid/setpoint_pc']):5.1f}  "
                f"PID={float(v['pid/salida_pid']):5.2f} V  valvula={float(v['DATOS_PAC/VAL_PROPOR']):4.1f} V  "
                f"bomba={'ON ' if v['DATOS_PAC/ACT_VARIADOR'] else 'OFF'}  selector={self.ent.selector}  "
                f"mando={'PC' if v['DATOS_PAC/PC_TPM'] else 'HMI'}")
