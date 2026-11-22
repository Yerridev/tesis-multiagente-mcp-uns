"""Modelo fisico del Modulo de Control de Presion MCP-09 (INDUCONTROL).

La bomba (variador Altivar 11, consigna 0-10 V) presuriza el tanque cerrado T2; la valvula
proporcional Danfoss EV260B (0-10 V = 0-100 %) descarga a T1. Modelo de primer orden no lineal:

  C * dP/dt = I(v) - K * apertura * sqrt(P)        I(v) = I_MAX * (v - v_min)/(1 - v_min)

Transmisor Danfoss MBS 3000 4-20 mA = 0..87,02 psi (el programa publica la corriente en A).
Parametros estimados (100 % bomba y 30 % valvula ~ 35 psi); calibrar con el historiador.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

PSI_FONDO_ESCALA = 87.02


@dataclass
class ParametrosPresion:
    i_max: float = 60.0
    velocidad_minima: float = 0.15
    k_valvula: float = 33.8
    capacidad: float = 20.0
    p_max: float = 80.0
    ruido_psi: float = 0.15
    rampa_variador_s: float = 8.0    # s de 0 a 10 V (rampa de aceleracion del Altivar)


@dataclass
class EstadoPresion:
    presion: float = 0.0
    agua_t1: bool = True
    sensor_congelado: bool = False
    valor_congelado: float | None = None
    fuga: float = 0.0            # apertura adicional (0..1) por fuga inyectada


class PlantaPresion:
    def __init__(self, p: ParametrosPresion | None = None, semilla: int | None = None):
        self.p = p or ParametrosPresion()
        self.e = EstadoPresion()
        self.rng = random.Random(semilla)
        self.var_real = 0.0          # tension que de verdad sigue el variador (con rampa)
        self.camino_bomba = 1.0      # 0 = llave V5 cerrada (planta simulada con llaves)
        self.camino_retorno = 1.0    # 0 = V2 y V3 cerradas: T2 no descarga

    def paso(self, dt: float, variador_v: float, valvula_v: float):
        p, e = self.p, self.e
        paso_v = 10.0 / p.rampa_variador_s * dt
        self.var_real += max(-paso_v, min(paso_v, max(0.0, min(10.0, variador_v)) - self.var_real))
        s = self.var_real / 10.0
        i = self.camino_bomba * p.i_max * (s - p.velocidad_minima) / (1 - p.velocidad_minima) if (s > p.velocidad_minima and e.agua_t1) else 0.0
        ap = min(1.0, max(0.0, valvula_v) / 10.0 * self.camino_retorno + e.fuga)
        o = p.k_valvula * max(ap, 0.02) * math.sqrt(max(0.0, e.presion))   # 2 % de fuga natural
        e.presion = max(0.0, min(p.p_max, e.presion + dt * (i - o) / p.capacidad))

    def corriente_a(self) -> float:
        e = self.e
        if e.sensor_congelado:
            if e.valor_congelado is None:
                e.valor_congelado = self._a()
            return e.valor_congelado
        e.valor_congelado = None
        return self._a()

    def _a(self) -> float:
        psi = max(0.0, self.e.presion + self.rng.gauss(0.0, self.p.ruido_psi))
        return 0.004 + 0.016 * min(psi, PSI_FONDO_ESCALA) / PSI_FONDO_ESCALA
