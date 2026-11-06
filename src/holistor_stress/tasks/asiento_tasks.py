"""Tareas que generan asientos de verdad. ⚠ Crean asientos (y con reemplazar=true borran los previos)."""

from __future__ import annotations

from locust import task

from holistor_stress.core.errores import SesionInvalidadaError
from holistor_stress.flows.trabajo_gdc import ejecutar_trabajo_gdc
from holistor_stress.tasks.base import TareaHolistor


class GenerarAsientoGdcTask(TareaHolistor):
    """Una iteración = un trabajo: generar → seguir la cola → resultado → verificar → trabajos.csv.

    Con `flujo.contexto: cada_iteracion` vuelve a abrir la pantalla antes de cada trabajo (sin
    repetir el precheck); con `una_vez` reutiliza el contexto del on_start.
    """

    def on_start(self) -> None:
        super().on_start()
        self._primera = True

    @task
    def trabajo(self) -> None:
        u = self.user
        if not u.asegurar_contexto():
            return
        if u.settings.flujo.contexto == "cada_iteracion" and not self._primera and not u.preparar(con_precheck=False):
            u.verificar_activo()
            return
        self._primera = False
        try:
            ejecutar_trabajo_gdc(u)
        except SesionInvalidadaError as e:
            u.detener(str(e))
            u.verificar_activo()
        u.trabajo_terminado()
