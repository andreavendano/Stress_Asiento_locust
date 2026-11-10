"""Sesión del usuario virtual: login una vez y re-login controlado ante un 401 (sesión única, R1)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from holistor_stress.api import auth
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core import metrics
from holistor_stress.core.errores import NoAutorizadoError, SesionInvalidadaError

logger = logging.getLogger("holistor_stress")
T = TypeVar("T")

N_RELOGIN = "[Sesión] re-login por 401"
N_INVALIDADA = "[Sesión] sesión invalidada"


def iniciar_sesion(user: UsuarioApi) -> None:
    """Login con la fila; deja el token en el contexto. Si falla, el contexto queda sin token.

    `login=gdc` (por defecto): Account/Authenticate del back de GDC. `login=plataforma`: login de la
    plataforma SaaS, que además deja el tenant (header Abp.TenantId) y el userId en el contexto.
    """
    user.ctx.token = None
    if user.ctx.fila.login == "plataforma":
        token, tenant_id, user_id = auth.authenticate_plataforma(user)
        user.ctx.abp_tenant_id, user.ctx.user_id = tenant_id, user_id
        user.ctx.token = token
        return
    user.ctx.token = auth.authenticate(user)


def con_sesion(user: UsuarioApi, paso: Callable[..., T], *args, **kwargs) -> T:
    """Ejecuta `paso`; ante un 401 re-loguea (hasta flujo.relogin_401_max veces) y lo reintenta.

    Con sesión única, un 401 casi siempre significa que alguien más inició sesión con este usuario
    (Postman, la UI u otro usuario virtual). Si el re-login no alcanza, se lanza SesionInvalidadaError.
    """
    maximo = user.settings.flujo.relogin_401_max
    intentos = 0
    while True:
        try:
            return paso(*args, **kwargs)
        except NoAutorizadoError as e:
            if intentos >= maximo:
                msg = (
                    f"{user.ctx.etiqueta} sesión invalidada (¿usuario usado en otra sesión?): "
                    f"401 después de {intentos} re-login"
                )
                metrics.registrar(user.environment, metrics.TIPO_SESION, N_INVALIDADA, error=msg)
                raise SesionInvalidadaError(msg) from e
            intentos += 1
            logger.warning("%s 401: re-login %d de %d", user.ctx.etiqueta, intentos, maximo)
            with metrics.cronometro() as ms:
                iniciar_sesion(user)
            metrics.registrar(user.environment, metrics.TIPO_SESION, N_RELOGIN, ms())
