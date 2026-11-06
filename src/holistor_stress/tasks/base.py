"""TaskSet base: si el usuario virtual quedó detenido en el setup, termina sin ejecutar tareas."""

from __future__ import annotations

from locust import TaskSet


class TareaHolistor(TaskSet):
    def on_start(self) -> None:
        # StopUser desde acá termina el usuario virtual sin traceback en el log (on_stop devuelve la fila).
        self.user.verificar_activo()
