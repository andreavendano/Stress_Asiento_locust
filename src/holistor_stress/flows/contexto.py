"""Preparar el contexto = abrir la pantalla Generar Asientos y completar sus filtros.

Lo reutilizan todos los escenarios: `smoke_contexto` solo hace esto; `asiento_gdc` (Fase 3) genera
después con el contexto resuelto.
"""

from __future__ import annotations

from holistor_stress.api.http import UsuarioApi
from holistor_stress.flows import gdc, seleccion
from holistor_stress.flows.sesion import con_sesion, iniciar_sesion


def preparar_contexto(user: UsuarioApi, con_precheck: bool = True) -> None:
    """Empresa + ejercicio + período (+ origen y precheck en GDC). Lanza las fallas de `core.errores`.

    Inicia sesión si todavía no hay token. Cada paso se reintenta una vez ante un 401 (re-login).
    `con_precheck` solo tiene efecto si `flujo.precheck` no es `off`.
    """
    ctx = user.ctx
    if not ctx.token:
        iniciar_sesion(user)
    ctx.limpiar_seleccion()
    con_sesion(user, seleccion.seleccionar_empresa_ejercicio, user)
    con_sesion(user, seleccion.seleccionar_periodo, user)
    if ctx.fila.modulo == "GDC":
        con_sesion(user, seleccion.seleccionar_origen, user)
        alcance = user.settings.flujo.precheck
        if con_precheck and alcance != "off":
            con_sesion(user, gdc.precheck, user, alcance)
