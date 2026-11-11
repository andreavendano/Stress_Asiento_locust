"""Usuario virtual del smoke de contexto: login + empresa + período + origen (NO crea asientos)."""

from __future__ import annotations

from holistor_stress.core.base_user import HolistorUser
from holistor_stress.tasks.contexto_tasks import ReabrirPantallaTask


class SmokeContextoUser(HolistorUser):
    modulos_fila = ("GDC", "SYJ")
    tasks = [ReabrirPantallaTask]
