"""Tareas de los escenarios de comprobantes: una iteración = un ciclo del escenario.

Con `--trabajos-por-usuario 1` cada usuario virtual hace un solo ciclo y la prueba termina sola (lo que
antes era SCENARIO=<escenario>); sin cuota repite hasta que termina la prueba (antes <escenario>_loop).
"""

from __future__ import annotations

from locust import task

from holistor_stress.core.errores import FallaDatos, SesionInvalidadaError
from holistor_stress.tasks.base import TareaHolistor


class CicloComprobantesTask(TareaHolistor):
    """El escenario lo define el usuario virtual (`escenario`: clase con `__init__(user)` y `ejecutar()`)."""

    def on_start(self) -> None:
        super().on_start()
        self.escenario = None

    @task
    def ciclo(self) -> None:
        u = self.user
        if not u.asegurar_contexto():
            return
        if self.escenario is None:
            try:
                self.escenario = u.escenario(u)
            except FallaDatos as e:  # configuración del ambiente o de la fila: no tiene sentido reintentar
                u.detener(str(e))
                u.verificar_activo()
        try:
            self.escenario.ejecutar()
        except SesionInvalidadaError as e:
            u.detener(str(e))
            u.verificar_activo()
        u.trabajo_terminado()
