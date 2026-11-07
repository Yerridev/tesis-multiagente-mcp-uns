"""Modelo fisico del Modulo de Control de Nivel MCN-09/001 (INDUCONTROL).

La bomba (variador ATV11) lleva agua del tanque de reserva T1 al tanque de proceso T2; T2 descarga
de vuelta a T1 por la valvula motorizada Belimo LRB24-3 (flotante, abrir/cerrar por tiempo).

  A * dh/dt = Q_bomba - Q_salida
  Q_bomba  = Q_MAX * (v - v_min)/(100 - v_min)   (0 si v < v_min o T1 sin agua)
  Q_salida = K_V * apertura * sqrt(h)

El sensor ultrasonico TS-30S mide DISTANCIA: N7:4 = 16348 - 400 * h_cm (satura en 0 cerca de 41 cm),
con ruido y picos de eco ocasionales (por eso el conector usa mediana de 3).
Parametros estimados; calibrar con datos del historiador.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class ParametrosNivel:
    area_cm2: float = 900.0          # seccion del tanque 2 (30 x 30 cm, supuesto)
    altura_cm: float = 60.0
    q_max_lpm: float = 20.0          # L/min con el variador al 100 %
    velocidad_minima: float = 15.0   # %
    k_valvula: float = 2.6           # L/min por (fraccion de apertura * sqrt(cm))
    carrera_valvula_s: float = 95.0  # tiempo de 0 a 100 % (calibrado: 9500 = 95 s)
    ruido_cuentas: float = 25.0
    prob_pico_eco: float = 0.01      # por lectura


@dataclass
class EstadoNivel:
    nivel_cm: float = 5.0
    apertura: float = 0.8            # 0..1 (el conector asume 80 % al arrancar)
    agua_t1: bool = True
    sensor_congelado: bool = False
    valor_congelado: int | None = None
    fuga_lpm: float = 0.0            # falla inyectable


class PlantaNivel:
    def __init__(self, p: ParametrosNivel | None = None, semilla: int | None = None):
        self.p = p or ParametrosNivel()
        self.e = EstadoNivel()
        self.rng = random.Random(semilla)

    def paso(self, dt: float, velocidad_pct: float, abriendo: bool, cerrando: bool):
        p, e = self.p, self.e
        if abriendo and not cerrando:
            e.apertura = min(1.0, e.apertura + dt / p.carrera_valvula_s)
        elif cerrando and not abriendo:
            e.apertura = max(0.0, e.apertura - dt / p.carrera_valvula_s)
        v = max(0.0, min(100.0, velocidad_pct))
        q_in = 0.0
        if e.agua_t1 and v > p.velocidad_minima:
            q_in = p.q_max_lpm * (v - p.velocidad_minima) / (100.0 - p.velocidad_minima)
        q_out = p.k_valvula * e.apertura * math.sqrt(max(0.0, e.nivel_cm)) + e.fuga_lpm
        dh = (q_in - q_out) * 1000.0 / 60.0 / p.area_cm2 * dt     # L/min -> cm3/s -> cm
        e.nivel_cm = max(0.0, min(p.altura_cm, e.nivel_cm + dh))

    def lectura_raw(self) -> int:
        e = self.e
        if e.sensor_congelado:
            if e.valor_congelado is None:
                e.valor_congelado = self._raw()
            return e.valor_congelado
        e.valor_congelado = None
        return self._raw()

    def _raw(self) -> int:
        x = 16348.0 - 400.0 * self.e.nivel_cm + self.rng.gauss(0.0, self.p.ruido_cuentas)
        if self.rng.random() < self.p.prob_pico_eco:
            x += self.rng.choice((-1, 1)) * self.rng.uniform(1500, 4000)
        return int(max(0, min(16536, x)))
