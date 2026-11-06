"""Servicio de login."""

from __future__ import annotations

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, llamar
from holistor_stress.core.errores import FallaDatos, FallaHttp

# Códigos con los que el servidor rechaza al usuario: reintentar no sirve.
RECHAZO_CREDENCIALES = (400, 401, 403)


def authenticate(user: UsuarioApi) -> str:
    """POST Account/Authenticate → accessToken. La clave solo viaja en el body, nunca en un mensaje."""
    fila = user.ctx.fila
    if fila.clave is None:
        raise FallaDatos(f"{fila.etiqueta} la fila no tiene clave (columna clave o variable de entorno)")
    body = {"email": fila.usuario, "password": fila.clave.get_secret_value(), "tenantId": fila.tenant_id}
    try:
        r = llamar(
            user,
            "POST",
            rutas.AUTHENTICATE,
            rutas.N_AUTHENTICATE,
            json=body,
            autenticado=False,
            validar=lambda d: None if isinstance(d, dict) and d.get("accessToken") else "login sin accessToken",
        )
    except FallaHttp as e:
        if e.status in RECHAZO_CREDENCIALES:
            raise FallaDatos(f"{e} · revisar usuario, clave y tenant de la fila {fila.id}") from e
        raise
    except FallaDatos as e:
        # 200 sin token es una anomalía del servidor, no de la fila.
        raise FallaHttp(str(e), status=200) from e
    return r.data["accessToken"]
