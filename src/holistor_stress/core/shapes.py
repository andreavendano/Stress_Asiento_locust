"""Rampa escalonada opcional (antes shapes.py): se activa con la variable LOAD_SHAPE=steps.

En vez de subir de golpe a N usuarios, sube por escalones y mantiene cada uno un tiempo, para ver en qué nivel
de carga el sistema empieza a degradarse.

    LOAD_STEPS = escalones "usuarios:spawn_rate:duracion_seg" separados por coma
    Ej.: LOAD_STEPS=50:5:300,100:5:300,250:10:600,500:10:600,1000:10:900

Con la rampa activa Locust IGNORA -u / -r / -t: la duración total es la suma de los escalones. Ojo: cada
usuario virtual necesita su propia fila en users.csv (sesión única).

Los locustfiles de comprobantes hacen `from holistor_stress.core.shapes import *`: si LOAD_SHAPE no es
"steps", no se exporta ninguna clase y Locust usa -u / -r / -t como siempre.
"""

from __future__ import annotations

import logging
import os

from locust import LoadTestShape

logger = logging.getLogger("holistor_stress")

DEFAULT_STEPS = "50:5:300,100:5:300,250:10:600,500:10:600,1000:10:900"


def parsear_escalones(texto: str) -> list[tuple[int, float, float]]:
    escalones = []
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        usuarios, ritmo, duracion = parte.split(":")
        escalones.append((int(usuarios), float(ritmo), float(duracion)))
    if not escalones:
        raise ValueError("LOAD_STEPS vacío")
    return escalones


class StepLoadShape(LoadTestShape):
    def __init__(self):
        super().__init__()
        self.escalones = parsear_escalones(os.getenv("LOAD_STEPS", DEFAULT_STEPS))
        total = sum(d for _, _, d in self.escalones)
        logger.warning("Rampa escalonada: %s (duración total %.0fs)", self.escalones, total)

    def tick(self):
        transcurrido, acumulado = self.get_run_time(), 0.0
        for usuarios, ritmo, duracion in self.escalones:
            acumulado += duracion
            if transcurrido < acumulado:
                return usuarios, ritmo
        return None  # fin de la prueba


__all__ = ["StepLoadShape"] if os.getenv("LOAD_SHAPE", "").strip().lower() == "steps" else []
