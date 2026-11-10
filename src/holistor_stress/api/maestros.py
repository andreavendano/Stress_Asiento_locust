"""Datos maestros de los escenarios de comprobantes: empresa, períodos fiscales, proveedor y tipos de movimiento."""

from __future__ import annotations

from holistor_stress.api import rutas
from holistor_stress.api.comprobantes import gdc
from holistor_stress.api.http import UsuarioApi


def empresas_by_tenant(user: UsuarioApi, filtro: dict) -> dict:
    return gdc(user, "POST", rutas.EMPRESAS_BY_TENANT, rutas.N_M_EMPRESAS, json={"filter": filtro, "search": ""})


def periodos_fiscales_empresa(user: UsuarioApi, emp: int) -> dict:
    """Todos los períodos de la empresa. El body es el de la UI: 'empCodigo' en la raíz da HTTP 400
    ("property empCodigo should not exist") y sin filtro el servicio devuelve solo 10 períodos."""
    body = {
        "page": 1,
        "limit": 100,
        "search": "",
        "sort": {"field": "periodoFiscalCod", "direction": "DESC"},
        "filter": {"empCodigo": int(emp)},
    }
    return gdc(user, "POST", rutas.PERIODOS_FISCALES, rutas.N_M_PERIODOS, json=body)


def proveedores(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.PROVEEDOR_CONSULTA, rutas.N_M_PROVEEDOR, json=body)


def movimiento_tipos(user: UsuarioApi, emp: int, body: dict) -> dict:
    return gdc(user, "POST", rutas.MOVIMIENTO_TIPOS, rutas.N_M_MOVTIPOS, params={"empCodigo": emp}, json=body)
