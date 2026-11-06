"""Servicios de origen del asiento y tipos de comprobante."""

from __future__ import annotations

from typing import Any

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, llamar


def origenes(user: UsuarioApi) -> Any:
    """GET origenes → {origenes[]: origenAsientoId, esComprobante, …}."""
    return llamar(user, "GET", rutas.ORIGENES, rutas.N_ORIGENES).data


def tipos_comprobante(user: UsuarioApi, origen_asiento_id: int) -> Any:
    """GET tipos-comprobante?origenAsientoId= → {tipoLote, tipos[]: tipoComprobanteId}."""
    params = {"origenAsientoId": origen_asiento_id}
    return llamar(user, "GET", rutas.TIPOS_COMPROBANTE, rutas.N_TIPOS_COMPROBANTE, params=params).data
