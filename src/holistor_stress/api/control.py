"""Servicios de control de GDC (tabla nuc_AsientosOtrosModulos y fechas de cada asiento)."""

from __future__ import annotations

from typing import Any

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, llamar


def jobs_estado(user: UsuarioApi, claves: dict[str, Any]) -> Any:
    """POST jobs/estado {asientos[]: empresa, ejercicio, idAsiento}.

    Devuelve {estado, total, aceptados, rechazados, pendientes}.
    """
    return llamar(user, "POST", rutas.JOBS_ESTADO, rutas.N_JOBS_ESTADO, json=claves).data


def resultado_proceso(user: UsuarioApi, claves: dict[str, Any]) -> Any:
    """POST resultado-proceso {asientos[]} → {lineas[]} con la fecha de cada asiento."""
    return llamar(user, "POST", rutas.RESULTADO_PROCESO, rutas.N_RESULTADO_PROCESO, json=claves).data
