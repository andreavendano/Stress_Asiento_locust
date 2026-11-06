"""Servicio de acceso a la empresa (empresa habilitada + ejercicios)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, llamar


def acceso(user: UsuarioApi, empresa: int, validar: Callable[[Any], str | None] | None = None) -> Any:
    """GET acceso?empCodigo= → {ejercicios[], ejercicioSeleccionadoCodigo}."""
    return llamar(user, "GET", rutas.ACCESO, rutas.N_ACCESO, params={"empCodigo": empresa}, validar=validar).data
