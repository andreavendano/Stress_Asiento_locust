"""Llamado HTTP común a todos los servicios: headers, timeout, desenvoltura ABP y registro de la falla.

Reglas:
- Cada request se registra en Locust con su nombre "[Grupo] servicio" (no con la URL).
- Si algo falla, la falla se marca en ese request con la etiqueta de la fila y se lanza la excepción
  de `core.errores` que corresponde. Los flujos deciden qué hacer con ella.
- Nunca se incluye el body enviado en un mensaje (el login lleva la clave).
"""

from __future__ import annotations

import json as _json_mod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from holistor_stress.config.settings import Settings
from holistor_stress.core.context import ContextoAsiento
from holistor_stress.core.errores import FallaDatos, FallaHttp, FallaPaso, NoAutorizadoError

MAX_DETALLE = 200


class UsuarioApi(Protocol):
    """Lo que la capa API necesita de un usuario virtual (HolistorUser o un doble de test)."""

    client: Any
    ctx: ContextoAsiento
    settings: Settings
    environment: Any


@dataclass(frozen=True)
class Respuesta:
    status: int
    data: Any  # `data` de ABP ya desenvuelto
    bytes: int


def desenvolver(cuerpo: Any) -> Any:
    """ABP envuelve en {success, data, error}; algunos servicios usan `result`."""
    if isinstance(cuerpo, dict):
        for clave in ("data", "result"):
            if clave in cuerpo:
                return cuerpo[clave]
    return cuerpo


def _json(resp) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def detalle_error(resp, cuerpo: Any) -> str:
    """Mensaje del servidor (ABP: error.message / error.details) o el inicio del texto de la respuesta."""
    partes: list[str] = []
    if isinstance(cuerpo, dict):
        err = cuerpo.get("error")
        if isinstance(err, dict):
            partes += [str(err.get(k)) for k in ("message", "details") if err.get(k)]
        elif isinstance(err, str) and err:
            partes.append(err)
        if cuerpo.get("message"):
            partes.append(str(cuerpo["message"]))
        if cuerpo.get("code") and not partes:
            partes.append(str(cuerpo["code"]))
        if cuerpo.get("errors"):  # validaciones de los servicios de comprobantes
            partes.append(_json_mod.dumps(cuerpo["errors"], ensure_ascii=False)[:300])
    texto = " | ".join(partes) if partes else (getattr(resp, "text", "") or "").strip()
    texto = " ".join(texto.split())
    return texto[:MAX_DETALLE] + ("…" if len(texto) > MAX_DETALLE else "")


def llamar(
    user: UsuarioApi,
    metodo: str,
    ruta: str,
    nombre: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
    autenticado: bool = True,
    esperado: Iterable[int] = (200,),
    validar: Callable[[Any], str | None] | None = None,
    error_validacion: type[FallaPaso] = FallaDatos,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    crudo: bool = False,
    exigir_success: bool = False,
) -> Respuesta:
    """Ejecuta el request y devuelve `data`. `validar(data)` devuelve un mensaje si el negocio no cierra.

    Opcionales (los usan los escenarios de comprobantes):
    - `headers`: headers extra (por ejemplo el Content-Type de un multipart). `data`: body ya armado.
    - `crudo`: devuelve el JSON completo, sin desenvolver `data`/`result` (hay servicios con datos en la raíz).
    - `exigir_success`: una respuesta con `success: false` es una falla aunque el código sea 2xx.

    Lanza:
    - `NoAutorizadoError` ante un 401 en un servicio autenticado.
    - `FallaHttp` ante un código inesperado, sin respuesta o con una respuesta que no es JSON.
    - `error_validacion` (por defecto `FallaDatos`) si `validar` devuelve un mensaje; la falla queda
      en este request.
    """
    s, etq = user.settings, user.ctx.etiqueta
    esperado = tuple(esperado)
    enviar = {"Accept-Language": s.idioma}
    tenant_abp = getattr(user.ctx, "abp_tenant_id", None)
    if tenant_abp:  # login=plataforma: los servicios esperan el tenant en el header (como el front)
        enviar["Abp.TenantId"] = str(tenant_abp)
    if headers:
        enviar.update(headers)
    if autenticado:
        if not user.ctx.token:
            raise NoAutorizadoError(f"{etq} {nombre}: sin token (no se inició sesión)", status=None)
        enviar["Authorization"] = f"Bearer {user.ctx.token}"

    extra = {"data": data} if data is not None else {}
    with user.client.request(
        metodo,
        ruta,
        name=nombre,
        json=json,
        params=params,
        headers=enviar,
        timeout=s.timeout_request_s,
        catch_response=True,
        **extra,
    ) as resp:
        codigo = resp.status_code or 0
        if codigo == 0:
            causa = getattr(resp, "error", None)
            msg = f"{etq} sin respuesta: {type(causa).__name__ if causa else 'error de conexión'}"
            resp.failure(msg)
            raise FallaHttp(msg, status=0)

        cuerpo = _json(resp)
        if codigo == 401 and autenticado:
            msg = f"{etq} HTTP 401: token rechazado"
            resp.failure(msg)
            raise NoAutorizadoError(msg, status=401)
        if codigo not in esperado:
            msg = f"{etq} HTTP {codigo} (se esperaba {'/'.join(map(str, esperado))}): {detalle_error(resp, cuerpo)}"
            resp.failure(msg)
            raise FallaHttp(msg, status=codigo)
        if cuerpo is None:
            msg = f"{etq} HTTP {codigo} sin JSON: {detalle_error(resp, cuerpo)}"
            resp.failure(msg)
            raise FallaHttp(msg, status=codigo)

        if exigir_success and isinstance(cuerpo, dict) and cuerpo.get("success") is False:
            msg = f"{etq} success=false: {detalle_error(resp, cuerpo)}"
            resp.failure(msg)
            raise FallaHttp(msg, status=codigo)

        data = cuerpo if crudo else desenvolver(cuerpo)
        problema = validar(data) if validar else None
        if problema:
            msg = f"{etq} {problema}"
            resp.failure(msg)
            raise error_validacion(msg)

        resp.success()
        return Respuesta(status=codigo, data=data, bytes=len(getattr(resp, "content", b"") or b""))


def navegar(
    user: UsuarioApi,
    metodo: str,
    url: str,
    nombre: str,
    *,
    json: Any = None,
    headers: dict[str, str] | None = None,
) -> int:
    """Request de navegación (páginas, banners, lookups que la pantalla pide y el flujo no usa).

    Como el navegador: lleva el token y el tenant, no corta el flujo y solo se marca como falla si no hay
    respuesta o el código es >= 400. Devuelve el código HTTP (0 = sin respuesta).
    """
    enviar: dict[str, str] = {}
    tenant_abp = getattr(user.ctx, "abp_tenant_id", None)
    if tenant_abp:
        enviar["Abp.TenantId"] = str(tenant_abp)
    if user.ctx.token:
        enviar["Authorization"] = f"Bearer {user.ctx.token}"
    if headers:
        enviar.update(headers)
    with user.client.request(
        metodo,
        url,
        name=nombre,
        json=json,
        headers=enviar,
        timeout=user.settings.timeout_request_s,
        catch_response=True,
    ) as resp:
        codigo = resp.status_code or 0
        if codigo == 0:
            causa = getattr(resp, "error", None)
            resp.failure(f"{user.ctx.etiqueta} sin respuesta: {type(causa).__name__ if causa else 'error de conexión'}")
        elif codigo >= 400:
            resp.failure(f"{user.ctx.etiqueta} HTTP {codigo}: {detalle_error(resp, _json(resp))}")
        else:
            resp.success()
        return codigo
