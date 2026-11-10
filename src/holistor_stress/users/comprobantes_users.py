"""Usuarios virtuales de los escenarios de comprobantes (los importan los locustfiles).

Cada uno toma solo las filas de su módulo de users.csv (`modulos_fila`), inicia sesión una vez, resuelve los
datos maestros que necesita su escenario y en cada iteración ejecuta un ciclo.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime

from locust import task

from holistor_stress.api import importacion as api_impo
from holistor_stress.core.base_user import HolistorUser
from holistor_stress.core.contexto_comprobantes import ContextoComprobantes
from holistor_stress.core.errores import FallaPaso, SesionInvalidadaError
from holistor_stress.flows import maestros
from holistor_stress.flows.comprobante import ComprobanteCompleto, ComprobanteLite
from holistor_stress.flows.importacion import Importacion
from holistor_stress.flows.modificacion import ModificacionMasiva
from holistor_stress.flows.sesion import con_sesion
from holistor_stress.tasks.base import TareaHolistor
from holistor_stress.tasks.comprobantes_tasks import CicloComprobantesTask

logger = logging.getLogger("holistor_stress")


class ComprobantesUser(HolistorUser):
    abstract = True
    requeridos: tuple[str, ...] = maestros.REQ_MODIFICACION
    escenario = None  # clase del flujo (Importacion, ModificacionMasiva, …)
    # Sin `tasks` acá: Locust SUMA las tareas de la clase base a las de cada subclase, y el sondeo
    # terminaría ejecutando también la tarea de ciclo. Cada usuario concreto declara la suya.

    def nuevo_contexto(self, fila) -> ContextoComprobantes:
        return ContextoComprobantes(fila=fila)

    def preparar_contexto(self, con_precheck: bool) -> None:
        maestros.preparar_maestros(self, self.requeridos)


class ImportacionComprasUser(ComprobantesUser):
    """Importación de comprobantes de compra. ⚠ Crea comprobantes reales en el período de la fila."""

    modulos_fila = ("IMPO",)
    requeridos = maestros.REQ_IMPORTACION
    escenario = Importacion
    tasks = [CicloComprobantesTask]


class ModificacionMasivaUser(ComprobantesUser):
    """Modificación masiva de cabecera. ⚠ Modifica comprobantes reales del período de la fila."""

    modulos_fila = ("MODIF",)
    requeridos = maestros.REQ_MODIFICACION
    escenario = ModificacionMasiva
    tasks = [CicloComprobantesTask]


class ComprobanteLiteUser(ComprobantesUser):
    """Crear comprobante de compra, solo los requests imprescindibles. ⚠ Crea comprobantes reales."""

    modulos_fila = ("CPBTE",)
    requeridos = maestros.REQ_COMPROBANTE
    escenario = ComprobanteLite
    tasks = [CicloComprobantesTask]


class ComprobanteCompletoUser(ComprobantesUser):
    """Crear comprobante de compra con la navegación completa (113 pasos). ⚠ Crea comprobantes reales."""

    modulos_fila = ("CPBTE",)
    requeridos = maestros.REQ_COMPROBANTE
    escenario = ComprobanteCompleto
    tasks = [CicloComprobantesTask]


# ─────────────── Sondeo de "importación en curso" (diagnóstico del 409 IMPORT_ALREADY_RUNNING) ───────────────


class SondearEstadoTask(TareaHolistor):
    """Consulta el mismo servicio del paso IMPO 02 y escribe cada respuesta en sondeo.csv. No importa nada."""

    def on_start(self) -> None:
        super().on_start()
        self.archivo = None

    @task
    def estado(self) -> None:
        u = self.user
        if not u.asegurar_contexto():
            return
        m = u.ctx.maestros
        try:
            d = con_sesion(u, api_impo.estado_compras, u, m.emp_codigo, m.periodo_fiscal_id).get("data") or {}
            http = "OK"
        except SesionInvalidadaError as e:
            u.detener(str(e))
            u.verificar_activo()
            return
        except FallaPaso as e:
            d, http = {}, str(e).removeprefix(u.ctx.etiqueta).strip()
        if self.archivo is None and u.rt.carpeta_reportes is not None:
            self.archivo = u.rt.carpeta_reportes / "sondeo.csv"
            with self.archivo.open("w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f, delimiter=";").writerow(["hora", "fila", "http", "enCurso", "data"])
        ahora = datetime.now().strftime("%H:%M:%S")
        if self.archivo is not None:
            with self.archivo.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f, delimiter=";").writerow([ahora, u.ctx.fila.id, http, d.get("enCurso"), d])
        logger.info("[SONDEO] %s %s %s enCurso=%s %s", u.ctx.etiqueta, ahora, http, d.get("enCurso"), d)


class SondeoImportacionUser(ComprobantesUser):
    modulos_fila = ("IMPO",)
    requeridos = maestros.REQ_MODIFICACION
    tasks = [SondearEstadoTask]

    def wait_time(self) -> float:
        cfg = self.settings.importacion
        return cfg.intervalo_sondeo_s if cfg else 5.0
