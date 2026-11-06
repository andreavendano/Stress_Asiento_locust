"""Servicios de períodos del ejercicio y período fiscal."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, llamar


def periodos(user: UsuarioApi, empresa: int, ejercicio: int, validar: Callable[[Any], str | None] | None = None) -> Any:
    """GET periodos?empCodigo=&ejCodigo= → {periodos[]: codigo AAAAMM, desde, hasta, personalizado}."""
    params = {"empCodigo": empresa, "ejCodigo": ejercicio}
    return llamar(user, "GET", rutas.PERIODOS, rutas.N_PERIODOS, params=params, validar=validar).data


def periodos_fiscales(user: UsuarioApi, busqueda: str, limite: int = 100) -> Any:
    """POST GdcPeriodo/GetPeriodosFiscales {page, limit, search} → lista de períodos fiscales."""
    body = {"page": 1, "limit": limite, "search": busqueda}
    return llamar(user, "POST", rutas.PERIODOS_FISCALES, rutas.N_PERIODOS_FISCALES, json=body).data
