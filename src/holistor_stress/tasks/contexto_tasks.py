"""Tareas del smoke de contexto: abrir la pantalla Generar Asientos, sin generar asientos."""

from __future__ import annotations

from locust import task

from holistor_stress.tasks.base import TareaHolistor


class ReabrirPantallaTask(TareaHolistor):
    """Cada iteración vuelve a consultar empresa, período y origen con el MISMO token.

    Sirve para confirmar que con N usuarios en paralelo ninguno pierde la sesión (sin 401 por
    sesión cruzada) y para medir los servicios de la pantalla sin crear asientos. El precheck se
    ejecutó una sola vez, en el on_start.
    """

    def on_start(self) -> None:
        super().on_start()
        self._primera = True

    @task
    def reabrir_pantalla(self) -> None:
        u = self.user
        if not u.ctx.listo:  # quedó incompleto por una falla transitoria: se reintenta
            u.asegurar_contexto()
            return
        if self._primera:  # el on_start acaba de prepararlo: la primera iteración solo espera
            self._primera = False
            return
        u.preparar(con_precheck=False)
        u.verificar_activo()
