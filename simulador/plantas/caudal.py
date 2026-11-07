"""Modelo fisico del Modulo de Control de Caudal MCC-09 (INDUCONTROL).

Bomba centrifuga con variador de frecuencia que impulsa agua del tanque T1 a traves de una
valvula proporcional y del caudalimetro Kobold DRG (4-20 mA).

  caudal_objetivo = Q_MAX * f(velocidad) * g(apertura_valvula)
  tau * dQ/dt = caudal_objetivo - Q        (dinamica de primer orden de la tuberia/bomba)

f: la bomba no mueve agua por debajo de ~15 % de velocidad (presion insuficiente).
g: caracteristica de la valvula (raiz cuadrada, aprox. de igual porcentaje suavizada).
Parametros estimados; calibrar con datos del historiador si se necesita mas precision.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class ParametrosCaudal:
    q_max: float = 100.0          # L/min con bomba y valvula al 100 %
    velocidad_minima: float = 15.0  # % por debajo del cual no hay caudal
    tau: float = 1.5              # s, constante de tiempo del caudal
    ruido: float = 0.4            # L/min, desviacion del caudalimetro


@dataclass
class EstadoCaudal:
    caudal: float = 0.0
    sensor_congelado: bool = False
    valor_congelado: float | None = None
    obstruccion: float = 0.0      # 0..1, fraccion de la tuberia obstruida (falla inyectable)
    agua_ok: bool = True          # False = tanque T1 sin agua (la bomba no impulsa)


class PlantaCaudal:
    def __init__(self, p: ParametrosCaudal | None = None, semilla: int | None = None):
        self.p = p or ParametrosCaudal()
        self.e = EstadoCaudal()
        self.rng = random.Random(semilla)

    def paso(self, dt: float, bomba_on: bool, velocidad_pct: float, valvula_pct: float):
        p, e = self.p, self.e
        v = max(0.0, min(100.0, velocidad_pct))
        f = 0.0 if (not bomba_on or not e.agua_ok or v <= p.velocidad_minima) else \
            (v - p.velocidad_minima) / (100.0 - p.velocidad_minima)
        g = math.sqrt(max(0.0, min(100.0, valvula_pct)) / 100.0)
        objetivo = p.q_max * f * g * (1.0 - e.obstruccion)
        e.caudal += (objetivo - e.caudal) * min(1.0, dt / p.tau)

    def lectura(self) -> float:
        e = self.e
        if e.sensor_congelado:
            if e.valor_congelado is None:
                e.valor_congelado = e.caudal
            return e.valor_congelado
        e.valor_congelado = None
        return max(0.0, e.caudal + self.rng.gauss(0.0, self.p.ruido))
