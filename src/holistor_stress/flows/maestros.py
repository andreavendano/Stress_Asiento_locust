"""Datos maestros de los escenarios de comprobantes (antes `BaseTaskSet._lookup_master_data`).

Todo sale de la API con el token del propio usuario, sin ids fijos de un tenant:
- empresa: la de la fila (`empresa`), buscada EXACTAMENTE en GetEmpresasByTenant;
- período fiscal: el mes de la fila (`periodo`) de esa empresa;
- proveedor: el primer proveedor real y activo de la empresa (con búsquedas cada vez más amplias);
- tipos de movimiento: dos tipos gravados de compras (clase GR, C).

Cada escenario pide solo lo que usa (`REQ_*`). Si falta un dato, es una falla de datos y el usuario virtual
se detiene con un mensaje claro. Con `maestros.cache` (por defecto), el primer usuario virtual de cada
tenant/empresa/período hace los lookups y el resto los reutiliza.
"""

from __future__ import annotations

import logging
import threading

from holistor_stress.api import maestros as api
from holistor_stress.api.comprobantes import lista
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.contexto_comprobantes import Maestros
from holistor_stress.core.errores import FallaDatos, FallaHttp
from holistor_stress.flows.sesion import con_sesion, iniciar_sesion

logger = logging.getLogger("holistor_stress")

_PERIODO = ("emp_codigo", "periodo_fiscal_id", "periodo_fiscal_cod")
REQ_MODIFICACION = _PERIODO
REQ_IMPORTACION = (*_PERIODO, "proveedor_id", "proveedor_nro_doc")
REQ_COMPROBANTE = (*_PERIODO, "proveedor_id", "proveedor_tipo_doc", "proveedor_nro_doc",
                   "mov_tipo_id_venta_neta", "mov_tipo_id_iva_cinco")  # fmt: skip
_PROVEEDOR = {"proveedor_id", "proveedor_tipo_doc", "proveedor_nro_doc"}
_MOVTIPOS = {"mov_tipo_id_venta_neta", "mov_tipo_id_iva_cinco"}

# Tabla estándar de ARCA: abreviatura → código de tipo de documento.
TIPO_DOC_AFIP = {"CUIT": 80, "CUIL": 86, "DNI": 96, "LC": 90, "LE": 89, "PAS": 94, "CI": 92}

_CACHE: dict[tuple, Maestros] = {}
_LOCKS: dict[tuple, threading.Lock] = {}
_LOCK_GLOBAL = threading.Lock()


def limpiar_cache() -> None:
    with _LOCK_GLOBAL:
        _CACHE.clear()
        _LOCKS.clear()


def preparar_maestros(user: UsuarioApi, requeridos: tuple[str, ...]) -> None:
    """Login (si hace falta) + datos maestros en `ctx.maestros`. Lanza las fallas de `core.errores`."""
    ctx = user.ctx
    if not ctx.token:
        iniciar_sesion(user)
    ctx.maestros = None
    if not user.settings.maestros.cache:
        ctx.maestros = resolver(user, requeridos)
        return
    clave = (ctx.fila.tenant_id, ctx.fila.empresa, ctx.fila.periodo, requeridos)
    with _LOCK_GLOBAL:
        lock = _LOCKS.setdefault(clave, threading.Lock())
    with lock:
        m = _CACHE.get(clave)
        if m is None:
            m = _CACHE[clave] = resolver(user, requeridos)
        else:
            logger.info("%s datos maestros desde la cache del tenant (sin requests)", ctx.etiqueta)
    ctx.maestros = m


def resolver(user: UsuarioApi, requeridos: tuple[str, ...]) -> Maestros:
    ctx = user.ctx
    etq, emp_fila, mes = ctx.etiqueta, ctx.fila.empresa, ctx.fila.periodo
    datos: dict = {}
    datos.update(_empresa(user, emp_fila))
    datos.update(_periodo(user, datos["emp_codigo"], mes))
    if _PROVEEDOR & set(requeridos):
        datos.update(_proveedor(user, datos["emp_codigo"]))
    if _MOVTIPOS & set(requeridos):
        datos.update(_movimiento_tipos(user, datos["emp_codigo"]))
    faltan = [c for c in requeridos if datos.get(c) in (None, "")]
    if faltan:
        raise FallaDatos(f"{etq} datos maestros incompletos (empresa {emp_fila}, período {mes}): faltan {faltan}")
    m = Maestros(**datos)
    logger.info(
        "%s maestros OK: empresa=%s período=%s (id %s) proveedor=%s movTipos=(%s, %s)",
        etq, m.emp_codigo, m.periodo_fiscal_cod, m.periodo_fiscal_id, m.proveedor_id,
        m.mov_tipo_id_venta_neta, m.mov_tipo_id_iva_cinco,
    )  # fmt: skip
    return m


def _variantes(user: UsuarioApi, llamada, cuerpos: list, encontrar):
    """Prueba cada variante del body hasta que `encontrar(json)` devuelva algo. Un error HTTP pasa a la
    siguiente variante; si todas fallaron por HTTP, se relanza el último (falla transitoria)."""
    ultimo: FallaHttp | None = None
    alguna_ok = False
    for cuerpo in cuerpos:
        try:
            j = con_sesion(user, llamada, user, *cuerpo)
        except FallaHttp as e:
            ultimo = e
            continue
        alguna_ok = True
        encontrado = encontrar(j)
        if encontrado:
            return encontrado
    if ultimo is not None and not alguna_ok:
        raise ultimo
    return None


def _empresa(user: UsuarioApi, emp: int) -> dict:
    """La empresa EXACTA de la fila (no la primera que aparezca)."""

    def buscar(j):
        for e in lista(j, "data.items", "data", "items", "result.items", "result") or []:
            cod = e.get("empCodigo") or e.get("codigo") or e.get("id")
            if cod is not None and int(cod) == int(emp):
                return e
        return None

    filtros = [({"appModCod": "GDC", "activo": True},), ({"appModCod": "GDC"},), ({},)]
    e = _variantes(user, api.empresas_by_tenant, filtros, buscar)
    if e is None:
        raise FallaDatos(
            f"{user.ctx.etiqueta} no existe la empresa {emp} en este tenant (GetEmpresasByTenant no la devuelve)"
        )
    razon = e.get("empRazon") or e.get("empDescripcion") or e.get("empCodigoChr") or ""
    return {"emp_codigo": int(e.get("empCodigo") or e.get("codigo") or e.get("id")), "empresa_razon": str(razon)}


def _periodo(user: UsuarioApi, emp: int, mes: str) -> dict:
    j = con_sesion(user, api.periodos_fiscales_empresa, user, emp)
    todos = lista(j, "data.items", "data", "items", "result.items", "result") or []
    propios = [p for p in todos if p.get("empCodigo") is not None and int(p["empCodigo"]) == int(emp)]

    def cod(p):
        return str(p.get("periodoFiscalCod") or p.get("codigo") or p.get("cod") or "").strip()

    elegido = next((p for p in propios if cod(p) == str(mes)), None)
    if elegido is None and propios:
        # Igual que el proyecto original: se usa el primer período de la MISMA empresa, con aviso.
        elegido = propios[0]
        logger.warning(
            "%s el período %s no existe en la empresa %s: se usa el primero disponible (id=%s cod=%s)",
            user.ctx.etiqueta, mes, emp, elegido.get("periodoFiscalId"), cod(elegido),
        )  # fmt: skip
    if elegido is None:
        raise FallaDatos(
            f"{user.ctx.etiqueta} la empresa {emp} no tiene períodos fiscales: crear el período {mes} en GDC"
        )
    pid = elegido.get("periodoFiscalId") or elegido.get("id")
    return {
        "periodo_fiscal_id": int(pid) if pid is not None else None,
        "periodo_fiscal_cod": cod(elegido) or None,
        "periodos": tuple(propios),
    }


def _proveedor(user: UsuarioApi, emp: int) -> dict:
    """Primer proveedor real de la empresa. Si no hay con el filtro estricto, se van quitando condiciones."""
    variantes = [
        {"empCodigo": emp, "tipoEntidad": "P", "page": 1, "limit": 50, "activo": True,
         "filter": {"clienteProveedorProveedor": True}},
        {"empCodigo": emp, "tipoEntidad": "P", "page": 1, "limit": 50, "filter": {"clienteProveedorProveedor": True}},
        {"empCodigo": emp, "tipoEntidad": "P", "page": 1, "limit": 50, "filter": {}},
        {"empCodigo": emp, "page": 1, "limit": 50, "activo": True, "filter": {}},
        {"empCodigo": emp, "page": 1, "limit": 50, "filter": {}},
    ]  # fmt: skip
    items = _variantes(user, api.proveedores, [(v,) for v in variantes], lista)
    if not items:
        logger.warning("%s la empresa %s no tiene proveedores ni clientes", user.ctx.etiqueta, emp)
        return {}
    es_prov = [i for i in items if bool(i.get("clienteProveedorProveedor"))]
    prov = (
        next((i for i in es_prov if bool(i.get("activo")) or i.get("activo") is None), None)
        or (es_prov[0] if es_prov else None)
        or next((i for i in items if bool(i.get("activo"))), None)
        or items[0]
    )
    pid = prov.get("clienteProveedorId") or prov.get("id") or prov.get("cliProvId") or prov.get("clieprovId")
    rz = (prov.get("clienteProveedorRzSocial") or prov.get("razonSocial") or prov.get("rz")
          or prov.get("denominacion") or prov.get("nombre"))  # fmt: skip
    tdoc = (prov.get("tipoDocumentoId") or prov.get("tipoDocId") or prov.get("documentoTipoId")
            or prov.get("condFiscalCodigo") or prov.get("tipoDoc"))  # fmt: skip
    ndoc = (prov.get("clienteProveedorNroDoc") or prov.get("numeroDocumento") or prov.get("nroDoc")
            or prov.get("cuit") or prov.get("cuil") or prov.get("nroDocumento"))  # fmt: skip
    provin = (prov.get("provinciaId") or prov.get("provin") or prov.get("provincia") or prov.get("provId")
              or prov.get("clienteProveedorProvId"))  # fmt: skip
    abrev = str(prov.get("tipoDocAbrev") or "").strip().upper() or None

    datos: dict = {"proveedor_rz": str(rz) if rz is not None else None, "proveedor_tipo_doc_abrev": abrev}
    datos["proveedor_id"] = _entero(pid)
    t = _entero(tdoc)
    datos["proveedor_tipo_doc"] = t if t is not None and 1 <= t <= 99 else TIPO_DOC_AFIP.get(abrev or "")
    if ndoc is not None:
        limpio = str(ndoc).replace("-", "").replace(" ", "").replace(".", "")
        datos["proveedor_nro_doc"] = int(limpio) if limpio.isdigit() else None
    datos["proveedor_provincia_id"] = _entero(provin)
    return datos


def _movimiento_tipos(user: UsuarioApi, emp: int) -> dict:
    """Dos tipos de movimiento gravados de compras (clase GR, C). Con uno solo, se usa en los dos detalles."""
    orden = {"field": "movimientoTipoDesc", "direction": "ASC"}
    filtros = [
        {"MovimientoTipoClase": ["GR"], "MovimientoTipoCpraVta": "C", "MovimientoTipoActivo": True},
        {"MovimientoTipoClase": ["GR"], "MovimientoTipoCpraVta": "C"},
        {"MovimientoTipoClase": ["GR"]},
        {},
    ]
    cuerpos = [(emp, {"page": 1, "limit": 50, "sort": orden, "filter": f}) for f in filtros]
    items = _variantes(user, api.movimiento_tipos, cuerpos, lista)
    if not items:
        logger.warning("%s la empresa %s no tiene tipos de movimiento", user.ctx.etiqueta, emp)
        return {}

    def mid(i):
        return _entero(i.get("movimientoTipoId") or i.get("id") or i.get("MovimientoTipoId"))

    primero = mid(items[0])
    segundo = mid(items[1]) if len(items) >= 2 else primero
    return {"mov_tipo_id_venta_neta": primero, "mov_tipo_id_iva_cinco": segundo}


def _entero(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
