"""PLC virtual Allen-Bradley MicroLogix 1100 (1763) + 1762-IF2OF2 del modulo de nivel MCN-09/001.

Mismo mapa que conector_edge_ml1100.py y conector_control_nivel.py (funcionan sin cambios):
  I:0/0 REMOTO  I:0/1 LOCAL  I:0/2 T1 con agua  I:0/3 T1 nivel alto  I:0/4 ARRANQUE  I:0/5 paro NC
  I:1.5 potenciometro   O:1.0 consigna PLC -> variador (0..32767)
  O:0/0 alarma nivel alto  O:0/1 nivel bajo T1  O:0/2 bomba  O:0/3 piloto marcha  O:0/4 abrir  O:0/5 cerrar
  B3:0/1 marcha interna  B3:0/3 PC_HMI (0=PC)  B3:0/4 START_PC  B3:0/5 START_HMI  B3:0/13 START_VALVU
  B3:0/14 OSR de START_PC (arranca solo con flanco 0->1)
  N7:1/N7:2 preset apertura/cierre (0.01 s) -> T4:0/T4:1   N7:4 PV (distancia)  N7:5 SP PC  N7:6 SP HMI
  N7:8..10 Kc/Ti/Td PC (x100)  N7:11..13 HMI  N7:14 CV del PID PD12:0 (0..16383)
  F8:4..6 nivel cm / CV % / SP cm (informativos)

PD12:0 se emula como PID ISA de accion DIRECTA (la PV es distancia: PV > SP = falta agua = mas bomba),
Ti en minutos, Td en minutos, muestreo 0,5 s. La escalera es una reconstruccion.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..plantas.nivel import PlantaNivel
from .enip_pccc import TablaDatos

B3, N7, F8, T4 = 3, 7, 8, 4
O, I = 0, 1
CV_MAX = 16383
PERIODO_PID = 0.5


@dataclass
class Entradas:
    selector: str = "remoto"      # remoto | local | off
    nivel_alto_t1: bool = False
    paro_ok: bool = True          # paro de emergencia NC
    arranque: bool = False        # pulsador (los escenarios dan un pulso)
    potenciometro: int = 14000    # cuentas I:1.5


class MicroLogixNivel:
    def __init__(self, planta: PlantaNivel, tabla: TablaDatos | None = None):
        self.planta = planta
        t = self.t = tabla or TablaDatos()
        t.crear(B3, 8); t.crear(N7, 64); t.crear(F8, 2 * 16); t.crear(T4, 3 * 4)
        t.poner(N7, 5, 16348)                # SP 0 cm = sin consigna hasta que la PC/HMI la cargue
        t.poner(N7, 6, 16348)
        t.poner(N7, 8, 300); t.poner(N7, 9, 50); t.poner(N7, 10, 0)   # Kc 3.0, Ti 0.5 min, Td 0
        t.poner(N7, 11, 300); t.poner(N7, 12, 50); t.poner(N7, 13, 0)
        self.ent = Entradas()
        self._start_prev = False
        self._valv_prev = False
        self._marcha_pc = False
        self._marcha_local = False
        self._integral = 0.0
        self._t_pid = 0.0
        self._pv_prev = None
        self._abrir_acc = self._cerrar_acc = None   # None = temporizador inactivo

    def scan(self, dt: float):
        t, e = self.t, self.ent
        # --- entradas fisicas ---
        t.poner_io_bit(I, 0, 0, e.selector == "remoto")
        t.poner_io_bit(I, 0, 1, e.selector == "local")
        t.poner_io_bit(I, 0, 2, self.planta.e.agua_t1)
        t.poner_io_bit(I, 0, 3, e.nivel_alto_t1)
        t.poner_io_bit(I, 0, 4, e.arranque)
        t.poner_io_bit(I, 0, 5, e.paro_ok)
        t.poner_io(I, 1, 5, e.potenciometro)
        remoto, local = t.io_bit(I, 0, 0), t.io_bit(I, 0, 1)
        agua, paro_ok = t.io_bit(I, 0, 2), t.io_bit(I, 0, 5)
        permiso = agua and paro_ok

        # --- marcha ---
        hmi = t.bit(B3, 3)
        start_pc = t.bit(B3, 4)
        flanco = start_pc and not self._start_prev        # OSR B3:0/14
        self._start_prev = start_pc
        t.poner_bit(B3, 14, flanco)
        if flanco and remoto and not hmi and permiso:
            self._marcha_pc = True
        if not start_pc or not remoto or hmi or not permiso:
            self._marcha_pc = False
        marcha_hmi = remoto and hmi and t.bit(B3, 5) and permiso
        if local and e.arranque and permiso:
            self._marcha_local = True
        if not local or not permiso:
            self._marcha_local = False
        marcha_remota = self._marcha_pc or marcha_hmi
        marcha = marcha_remota or self._marcha_local
        t.poner_bit(B3, 1, marcha)
        t.poner_io_bit(O, 0, 0, e.nivel_alto_t1)
        t.poner_io_bit(O, 0, 1, not agua)
        t.poner_io_bit(O, 0, 2, marcha)
        t.poner_io_bit(O, 0, 3, marcha)

        # --- medicion ---
        pv = self.planta.lectura_raw()
        t.poner(N7, 4, pv)

        # --- PID PD12:0 ---
        base = 11 if hmi else 8
        sp = t.palabra(N7, 6 if hmi else 5)
        kc, ti, td = t.palabra(N7, base) / 100.0, t.palabra(N7, base + 1) / 100.0, t.palabra(N7, base + 2) / 100.0
        if marcha_remota:
            self._t_pid += dt
            if self._t_pid >= PERIODO_PID:
                h, self._t_pid = self._t_pid, 0.0
                err = (pv - sp) / CV_MAX                     # accion directa, normalizado
                dpv = 0.0 if self._pv_prev is None else (pv - self._pv_prev) / CV_MAX / h
                self._pv_prev = pv
                if ti > 0 and kc > 0:
                    self._integral += err * h / (ti * 60.0)
                    lim = 1.0 / kc
                    self._integral = max(-lim, min(lim, self._integral))
                cv = kc * (err + self._integral + td * 60.0 * dpv)
                t.poner(N7, 14, round(max(0.0, min(1.0, cv)) * CV_MAX))
        else:
            self._integral, self._pv_prev, self._t_pid = 0.0, None, 0.0
            t.poner(N7, 14, 0)
        cv = t.palabra(N7, 14)
        t.poner_io(O, 1, 0, cv * 2 if marcha_remota else 0)

        # --- valvula temporizada (rungs START_VALVU / T4:0 / T4:1) ---
        sv = t.bit(B3, 13)
        if sv and not self._valv_prev:
            pre_a, pre_c = t.palabra(N7, 1), t.palabra(N7, 2)
            t.archivos[T4][1], t.archivos[T4][4] = pre_a & 0xFFFF, pre_c & 0xFFFF
            self._abrir_acc = 0.0 if pre_a > 0 else None
            self._cerrar_acc = 0.0 if pre_c > 0 and pre_a <= 0 else None
        self._valv_prev = sv
        abriendo = cerrando = False
        if self._abrir_acc is not None:
            self._abrir_acc += dt * 100
            abriendo = self._abrir_acc < t.archivos[T4][1]
            t.archivos[T4][2] = min(int(self._abrir_acc), 32767)
            if not abriendo:
                self._abrir_acc = None
        if self._cerrar_acc is not None:
            self._cerrar_acc += dt * 100
            cerrando = self._cerrar_acc < t.archivos[T4][4]
            t.archivos[T4][5] = min(int(self._cerrar_acc), 32767)
            if not cerrando:
                self._cerrar_acc = None
        t.poner_io_bit(O, 0, 4, abriendo)
        t.poner_io_bit(O, 0, 5, cerrando)

        # --- informativos ---
        t.poner_real(F8, 4, (16348 - pv) / 400.0)
        t.poner_real(F8, 5, 100.0 * cv / CV_MAX)
        t.poner_real(F8, 6, (16348 - sp) / 400.0)

        # --- fisica ---
        if marcha_remota:
            vel = 100.0 * cv / CV_MAX
        elif self._marcha_local:
            vel = min(100.0, 100.0 * e.potenciometro / 30770)   # ~60 Hz a 30770 cuentas
        else:
            vel = 0.0
        self.planta.paso(dt, vel, abriendo, cerrando)

    def resumen(self) -> str:
        t = self.t
        sp_cm = (16348 - t.palabra(N7, 5)) / 400
        return (f"h={self.planta.e.nivel_cm:5.1f} cm  SP={sp_cm:5.1f} cm  CV={100 * t.palabra(N7, 14) / CV_MAX:5.1f} %  "
                f"valvula={100 * self.planta.e.apertura:5.1f} %  bomba={'ON ' if t.io_bit(O, 0, 2) else 'OFF'}  "
                f"selector={self.ent.selector}  fuente={'HMI' if t.bit(B3, 3) else 'PC'}")
