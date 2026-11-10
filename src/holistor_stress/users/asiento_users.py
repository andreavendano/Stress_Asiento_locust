"""Usuarios virtuales que generan asientos."""

from __future__ import annotations

from holistor_stress.core.base_user import HolistorUser
from holistor_stress.tasks.asiento_tasks import GenerarAsientoGdcTask


class AsientoGdcUser(HolistorUser):
    """GDC de punta a punta. ⚠ Crea asientos reales en el ambiente."""

    modulos_fila = ("GDC",)
    tasks = [GenerarAsientoGdcTask]
