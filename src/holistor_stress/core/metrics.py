"""Métricas propias publicadas en las mismas tablas, gráficos y CSV de Locust.

Se usan para lo que no es un request HTTP: el setup de cada usuario virtual, los re-login por 401 y
(en la Fase 3) los tiempos de punta a punta de la cola.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

TIPO_FLUJO = "FLUJO"
TIPO_SESION = "SESION"
TIPO_SETUP = "SETUP"


def registrar(environment, tipo: str, nombre: str, ms: float = 0.0, error: BaseException | str | None = None) -> None:
    if isinstance(error, str):
        error = Exception(error)
    environment.events.request.fire(
        request_type=tipo,
        name=nombre,
        response_time=ms,
        response_length=0,
        response=None,
        context={},
        exception=error,
    )


@contextmanager
def cronometro():
    """`with cronometro() as ms: ...` → `ms()` devuelve los milisegundos transcurridos."""
    inicio = time.perf_counter()
    yield lambda: (time.perf_counter() - inicio) * 1000
