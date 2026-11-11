"""Servicios de Gestor de Comprobantes que usan los escenarios de comprobantes.

`gdc()` es el llamado común: pasa por `http.llamar` (headers, timeout, registro en Locust) y además
- devuelve el JSON completo (estos servicios ponen datos fuera de `data`: fileInfo, summary, canProceed…),
- trata `success: false` como falla aunque el código sea 2xx,
- antepone el nombre del paso al mensaje, para que la falla del ciclo diga en qué paso fue
  ("IMPO 04 Subir archivo: HTTP 500 …"), como en el proyecto original.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, detalle_error, llamar
from holistor_stress.core.errores import FallaHttp, FallaPaso, FallaTrabajo, NoAutorizadoError

OK_2XX = (200, 201, 202, 204)


def renombrar(e: FallaPaso, nombre: str, etiqueta: str) -> FallaPaso:
    """Misma falla (mismo tipo y status) con el nombre del paso delante del motivo."""
    motivo = str(e).removeprefix(etiqueta).strip()
    msg = f"{etiqueta} {nombre}: {motivo}"
    if isinstance(e, FallaHttp):
        return type(e)(msg, status=e.status)
    return type(e)(msg)


def gdc(
    user: UsuarioApi,
    metodo: str,
    ruta: str,
    nombre: str,
    *,
    json: Any = None,
    params: dict | None = None,
    data: bytes | None = None,
    headers: dict | None = None,
    validar: Callable[[Any], str | None] | None = None,
) -> dict:
    """Llama a un servicio y devuelve el JSON.

    `validar(json)` devuelve un mensaje si el paso no cierra (FallaTrabajo).
    """
    try:
        r = llamar(
            user,
            metodo,
            ruta,
            nombre,
            json=json,
            params=params,
            data=data,
            headers=headers,
            validar=lambda j: "respuesta no JSON" if not isinstance(j, dict) else (validar(j) if validar else None),
            error_validacion=FallaTrabajo,
            crudo=True,
            exigir_success=True,
            esperado=OK_2XX,
        )
    except NoAutorizadoError:
        raise  # con_sesion lo convierte en re-login
    except FallaPaso as e:
        raise renombrar(e, nombre, user.ctx.etiqueta) from e
    return r.data


def lista(j: Any, *rutas_json: str) -> list | None:
    """Primera lista encontrada en las rutas (anidadas con '.'). GdC usa "data" y ABP "result"."""
    for ruta in rutas_json or ("data.items", "data", "items", "result.items", "result"):
        nodo = j
        for clave in ruta.split("."):
            if isinstance(nodo, dict) and clave in nodo:
                nodo = nodo[clave]
            else:
                nodo = None
                break
        if isinstance(nodo, list):
            return nodo
    return None


def periodo_guion(cod: str | int) -> str:
    """Período fiscal AAAAMM → 'AAAA-MM' (formato de la grilla de comprobantes)."""
    cod = str(cod)
    return f"{cod[:4]}-{cod[4:6]}"


def grilla_compras(user: UsuarioApi, nombre: str, emp: int, periodo_cod: str, pagina: int = 1, limite: int = 1):
    """Grilla 'Comprobantes > Compras' del período (igual que la pantalla). Devuelve (items, total).

    Con limite=1 sirve para contar comprobantes.
    """
    periodo = periodo_guion(periodo_cod)
    j = gdc(
        user,
        "POST",
        rutas.GRILLA_COMPRAS,
        nombre,
        json={
            "page": pagina,
            "limit": limite,
            "empCodigo": emp,
            "periodoFiscalId": 0,
            "filter": {"periodoFiscalCodDesde": periodo, "periodoFiscalCodHasta": periodo},
        },
        validar=lambda j: None
        if isinstance((j.get("data") or {}).get("total"), int)
        else "la respuesta no trae 'total' de comprobantes",
    )
    d = j.get("data") or {}
    return d.get("items") or [], d["total"]


# ─────────────── Crear comprobante de compra ───────────────

_RUTAS_ID = [
    ("data", "id"), ("data", "ccpraId"), ("data", "ccPraId"), ("data", "CCPraId"), ("data", "cCPraId"),
    ("result", "id"), ("result", "ccpraId"), ("result", "ccPraId"), ("result", "cCPraId"), ("result", "CCPraId"),
    ("data", "result", "id"), ("data", "result", "ccpraId"), ("data", "result", "ccPraId"),
    ("data", "result", "CCPraId"),
    ("id",), ("ccpraId",), ("ccPraId",), ("cCPraId",), ("CCPraId",),
    ("data",), ("result",),
]  # fmt: skip
_CLAVES_ID = ("id", "ccpraId", "ccPraId", "CCPraId", "cCPraId")


def _positivo(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int) and v > 0:
        return v
    if isinstance(v, str) and v.isdigit() and int(v) > 0:
        return int(v)
    return None


def extraer_id_comprobante(body) -> int | None:
    """Id del comprobante recién creado: el back no es consistente con el nombre ni la ubicación del campo."""
    for camino in _RUTAS_ID:
        nodo, ok = body, True
        for k in camino:
            if isinstance(nodo, dict) and k in nodo:
                nodo = nodo[k]
            else:
                ok = False
                break
        if not ok:
            continue
        if (cid := _positivo(nodo)) is not None:
            return cid
        if isinstance(nodo, dict):
            for k in _CLAVES_ID:
                if k in nodo and (cid := _positivo(nodo[k])) is not None:
                    return cid
    return None


def _cabeceras(user: UsuarioApi) -> dict:
    h = {"Accept-Language": user.settings.idioma, "Content-Type": "application/json", "Accept": "*/*"}
    tenant_abp = getattr(user.ctx, "abp_tenant_id", None)
    if tenant_abp:
        h["Abp.TenantId"] = str(tenant_abp)
    if user.ctx.token:
        h["Authorization"] = f"Bearer {user.ctx.token}"
    return h


def crear_comprobante_compra(user: UsuarioApi, nombre: str, body: dict) -> tuple[int | None, str | None]:
    """POST /api/service/ComprobantesCompra. Devuelve (id, motivo): id del comprobante o el motivo por el que
    no se guardó. Como en el original: sin id pero con 2xx y sin aviso de duplicado, el request es OK."""
    etq = user.ctx.etiqueta
    with user.client.request("POST", rutas.COMPROBANTES_COMPRA, name=nombre, json=body, headers=_cabeceras(user),
                             timeout=user.settings.timeout_request_s, catch_response=True) as r:  # fmt: skip
        if r.status_code == 401:
            r.failure(f"{etq} HTTP 401: token rechazado")
            raise NoAutorizadoError(f"{etq} HTTP 401: token rechazado", status=401)
        try:
            j = r.json()
        except ValueError:
            j = {}
        cid = extraer_id_comprobante(j)
        if cid is not None:
            r.success()
            return cid, None
        if not r.status_code:
            motivo = f"sin respuesta del servidor: {type(getattr(r, 'error', None)).__name__}"
            r.failure(f"{etq} {motivo}")
            return None, motivo
        if r.status_code >= 400:
            motivo = f"HTTP {r.status_code} sin id: {detalle_error(r, j)}"
            r.failure(f"{etq} {motivo}")
            return None, motivo
        d = j.get("data") if isinstance(j, dict) else None
        if isinstance(d, dict) and (not d.get("saved", True) or d.get("duplicateWarning")):
            dw = d.get("duplicateWarning")
            codigo = str(dw.get("code", "")) if isinstance(dw, dict) else ""
            motivo = (f"comprobante NO guardado (saved={d.get('saved')} {codigo}) ccpraId={d.get('ccpraId')} "
                      f"quotaExceeded={d.get('quotaExceeded')}")  # fmt: skip
            r.failure(f"{etq} {motivo}")
            return None, motivo
        r.success()
        claves = list(j.keys()) if isinstance(j, dict) else type(j).__name__
        return None, f"HTTP {r.status_code} sin id del comprobante en la respuesta (claves={claves})"


def leer_comprobante_compra(user: UsuarioApi, nombre: str, cid: int) -> str | None:
    """GET /api/service/ComprobantesCompra/{id}. Devuelve None si se pudo leer, o el motivo de la falla."""
    etq = user.ctx.etiqueta
    with user.client.request("GET", f"{rutas.COMPROBANTES_COMPRA}/{cid}", name=nombre, headers=_cabeceras(user),
                             timeout=user.settings.timeout_request_s, catch_response=True) as r:  # fmt: skip
        if r.status_code == 401:
            r.failure(f"{etq} HTTP 401: token rechazado")
            raise NoAutorizadoError(f"{etq} HTTP 401: token rechazado", status=401)
        try:
            j = r.json()
        except ValueError:
            j = None
        if r.status_code == 200 and not (isinstance(j, dict) and j.get("success") is False):
            r.success()
            return None
        motivo = f"no se pudo leer el comprobante recién creado id={cid}: HTTP={r.status_code} {(r.text or '')[:200]!r}"
        r.failure(f"{etq} {motivo}")
        return motivo
