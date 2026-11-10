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


# Mensajes con los que ABP rechaza las credenciales (a veces con HTTP 500 en lugar de 401).
_CREDENCIALES_INVALIDAS = ("usuario o contrase", "inicio de sesi", "invalidusernameorpassword")


def authenticate_plataforma(user: UsuarioApi) -> tuple[str, int, str | None]:
    """Login por la plataforma SaaS: IsTenantAvailable (→ tenantId) + TokenAuth/Authenticate (→ token).

    Devuelve (accessToken, tenantId, userId). Es el login de los escenarios de comprobantes (cuentas `admin`
    por tenancy): el token sirve también en el back de Gestor de Comprobantes, con el header Abp.TenantId.
    """
    fila, plat = user.ctx.fila, user.settings.plataforma
    if plat is None:
        raise FallaDatos(f"{fila.etiqueta} login=plataforma sin la sección 'plataforma:' en el ambiente")
    if fila.clave is None:
        raise FallaDatos(f"{fila.etiqueta} la fila no tiene clave (columna clave o variable de entorno)")
    cabeceras = {
        "Content-Type": "application/json-patch+json",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": plat.portal_url,
        "Referer": f"{plat.portal_url}/account/login",
    }
    user.ctx.abp_tenant_id = None  # el primer paso va sin tenant

    def _tenant(d) -> str | None:
        if not isinstance(d, dict):
            return "IsTenantAvailable sin result"
        if d.get("state") not in (1, None) or d.get("tenantId") is None:
            return f"el tenant '{fila.tenancy}' no está disponible (state={d.get('state')})"
        return None

    r = llamar(
        user,
        "POST",
        f"{plat.host_url}{rutas.PLAT_IS_TENANT_AVAILABLE}",
        rutas.N_PLAT_CHECK_TENANT,
        json={"tenancyName": fila.tenancy},
        autenticado=False,
        headers=cabeceras,
        validar=_tenant,
    )
    tenant_id = int(r.data["tenantId"])
    if tenant_id != fila.tenant_id:
        raise FallaDatos(
            f"{fila.etiqueta} el tenant '{fila.tenancy}' es el {tenant_id} y la fila dice tenantId={fila.tenant_id}"
        )
    user.ctx.abp_tenant_id = tenant_id
    body = {"userNameOrEmailAddress": fila.usuario, "password": fila.clave.get_secret_value(), "rememberClient": False}
    try:
        r = llamar(
            user,
            "POST",
            f"{plat.host_url}{rutas.PLAT_TOKEN_AUTH}",
            rutas.N_PLAT_AUTHENTICATE,
            json=body,
            autenticado=False,
            headers=cabeceras,
            exigir_success=True,
            validar=lambda d: None if isinstance(d, dict) and d.get("accessToken") else "login sin accessToken",
        )
    except FallaHttp as e:
        if e.status in RECHAZO_CREDENCIALES or any(m in str(e).lower() for m in _CREDENCIALES_INVALIDAS):
            raise FallaDatos(f"{e} · revisar usuario, clave y tenancy de la fila {fila.id}") from e
        raise
    except FallaDatos as e:
        raise FallaHttp(str(e), status=200) from e
    uid = r.data.get("userId")
    return r.data["accessToken"], tenant_id, (str(uid) if uid is not None else None)
