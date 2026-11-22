"""Modelo fisico del Modulo de Control de Temperatura MCT-09 (INDUCONTROL).

Dos tanques de agua:
  - Principal (T2): tiene la resistencia calefactora (PWM por rele de estado solido).
  - Enfriador (T1): recibe agua de la bomba y puede enfriarse con el equipo de frio.
La bomba hace circular agua entre ambos tanques e intercambia calor.

Balance de energia (por tanque):
  C * dT/dt = P_entrada - UA * (T - T_amb) +/- intercambio_bomba (- enfriamiento)

Los parametros son estimaciones razonables (no medidas del equipo real); se pueden
ajustar con ParametrosTemperatura para calibrar contra datos del historiador.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

CP_AGUA = 4186.0  # J/(kg*K)


@dataclass
class ParametrosTemperatura:
    t_ambiente: float = 20.0          # C
    litros_principal: float = 20.0    # L de agua en el tanque principal
    litros_enfriador: float = 20.0    # L de agua en el tanque de enfriamiento
    potencia_resistencia: float = 2000.0  # W con la resistencia encendida
    ua_principal: float = 6.0         # W/K, perdidas al ambiente
    ua_enfriador: float = 6.0         # W/K
    caudal_bomba_max: float = 0.08    # L/s al 100 % del variador
    potencia_enfriador: float = 1200.0    # W que extrae el equipo de frio
    t_minima_enfriador: float = 12.0  # C, el equipo de frio no baja de aqui
    ruido_sensor: float = 0.35        # C, desviacion del ruido del transmisor


@dataclass
class EstadoTemperatura:
    t_principal: float = 20.0
    t_enfriador: float = 20.0
    # Fallas inyectables desde los escenarios
    sensor_congelado: bool = False
    valor_congelado_principal: float | None = None
    agua_principal_ok: bool = True    # False = el tanque principal se quedo sin agua
    agua_enfriador_ok: bool = True


class PlantaTemperatura:
    def __init__(self, p: ParametrosTemperatura | None = None, semilla: int | None = None):
        self.p = p or ParametrosTemperatura()
        self.e = EstadoTemperatura(t_principal=self.p.t_ambiente, t_enfriador=self.p.t_ambiente)
        self.rng = random.Random(semilla)

    def paso(self, dt: float, resistencia_on: bool, bomba_pct: float, enfriador_on: bool):
        """Integra el modelo dt segundos (Euler, dt pequeno)."""
        p, e = self.p, self.e
        c_p = p.litros_principal * CP_AGUA
        c_e = p.litros_enfriador * CP_AGUA

        q_res = p.potencia_resistencia if (resistencia_on and e.agua_principal_ok) else 0.0
        q_perd_p = p.ua_principal * (e.t_principal - p.t_ambiente)
        q_perd_e = p.ua_enfriador * (e.t_enfriador - p.t_ambiente)

        caudal = p.caudal_bomba_max * max(0.0, min(bomba_pct, 100.0)) / 100.0  # L/s ~ kg/s
        q_inter = caudal * CP_AGUA * (e.t_principal - e.t_enfriador)          # W de principal -> enfriador

        q_frio = p.potencia_enfriador if (enfriador_on and e.t_enfriador > p.t_minima_enfriador) else 0.0

        e.t_principal += dt * (q_res - q_perd_p - q_inter) / c_p
        e.t_enfriador += dt * (q_inter - q_perd_e - q_frio) / c_e

    def lectura_principal(self) -> float:
        """Lo que mide el transmisor del tanque principal (con ruido o congelado)."""
        e = self.e
        if e.sensor_congelado:
            if e.valor_congelado_principal is None:
                e.valor_congelado_principal = e.t_principal
            return e.valor_congelado_principal
        e.valor_congelado_principal = None
        return e.t_principal + self.rng.gauss(0.0, self.p.ruido_sensor)

    def lectura_enfriador(self) -> float:
        return self.e.t_enfriador + self.rng.gauss(0.0, self.p.ruido_sensor)
