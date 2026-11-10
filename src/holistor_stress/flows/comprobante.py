"""Crear comprobante de compra: variante LITE (antes tasks/gdc_lite.py) y COMPLETA (antes tasks/gdc.py).

LITE: solo lo imprescindible para crear 1 comprobante (≈7 requests por ciclo):
    /LITE/Lookups/…                        4 lookups que usa la pantalla para armar el comprobante
    /LITE/ComprobantesCompra/CREAR_(CORE)  crea el comprobante
    /LITE/ComprobantesCompra/GetById_…     lee 2 veces el detalle (solo si se creó)

COMPLETO: los 113 pasos de la grabación (ver flows/pasos_comprobante_completo.py).

Cada comprobante lleva entropía (fecha, punto de venta, tipo, importes y concepto) para no chocar con el
control de duplicados del back (DUPLICATE_VOUCHER → saved=False ccpraId=0).
"""

from __future__ import annotations

import calendar
import logging
import random
import uuid
from datetime import UTC, date, datetime, timedelta

from holistor_stress.api import comprobantes as api
from holistor_stress.api.http import UsuarioApi, navegar
from holistor_stress.core.contexto_comprobantes import Maestros
from holistor_stress.core.errores import FallaDatos, FallaTrabajo
from holistor_stress.flows import pasos_comprobante_completo as pasos
from holistor_stress.flows.ciclo import ejecutar_ciclo
from holistor_stress.flows.sesion import con_sesion

logger = logging.getLogger("holistor_stress")

PREFIJO = "CPBTE"
N_FLUJO_LITE = "CPBTE 00 Comprobante lite (punta a punta)"
N_FLUJO_COMPLETO = "CPBTE 00 Comprobante completo (punta a punta)"
N_CREAR_LITE = "/LITE/ComprobantesCompra/CREAR_(CORE)"
N_CREAR_COMPLETO = "/api/service/ComprobantesCompra"

_RAND = random.Random()
_TIPOS_COMP_LITE = (1, 2, 3, 6, 7, 8, 10, 11, 13)


def hoy() -> date:
    """Fecha de emisión = HOY (UTC, como el original)."""
    return datetime.now(UTC).date()


def cuerpo_comprobante(m: Maestros, variante: str, quien: str = "") -> dict:
    """Body de POST /api/service/ComprobantesCompra. NO agregar campos: la API valida estrictamente y
    "property X should not exist" hace que no se guarde el comprobante."""
    h = hoy()
    if variante == "lite":
        dia = _RAND.randint(1, calendar.monthrange(h.year, h.month)[1])  # todo el mes
        jit1, jit2 = _RAND.randint(1, 199999), _RAND.randint(100000, 999999)
        pto, tipo = _RAND.randint(1, 9999), _RAND.choice(_TIPOS_COMP_LITE)
    else:
        dia = _RAND.randint(1, h.day)  # del 1 a hoy
        jit1, jit2 = _RAND.randint(1, 999), _RAND.randint(100, 9999)
        pto, tipo = _RAND.randint(1, 50), _RAND.randint(1, 15)
    fecha = datetime.combine(h.replace(day=dia), datetime.min.time()) + timedelta(
        hours=_RAND.randint(0, 23), minutes=_RAND.randint(0, 59), seconds=_RAND.randint(0, 59)
    )
    emision = fecha.strftime("%Y-%m-%dT%H:%M:%S")
    if variante == "lite":
        concepto = (f"Stress Locust LITE {uuid.uuid4().hex[:20]} pVta={pto} tipoC={tipo} jitN1={jit1} jitN2={jit2} "
                    f"user={quien} H{fecha.hour}M{fecha.minute}S{fecha.second}")  # fmt: skip
    else:
        concepto = f"Stress Locust {uuid.uuid4().hex[:14]} dia={fecha.strftime('%Y-%m-%d')}"

    def detalle(mov_id, neto, porc):
        iva = round(neto * (porc / 100.0), 2)
        sub = round(neto + iva, 2)
        return {
            "CCpraDetMovId": mov_id, "CCpraDetRetPerId": None, "CCpraDetNeto": f"{neto:.2f}",
            "CCpraDetBonifMonto": "0.00", "CCpraDetNetoGravado": f"{neto:.2f}", "CCpraDetIVAPorc": porc,
            "CCpraDetIVAMonto": f"{iva:.2f}", "CCpraDetCredFiscal": f"{iva:.2f}", "CCpraDetSubtotal": f"{sub:.2f}",
            "CCpraDetProvin": None, "CCpraDetCueCon": None, "CCpraDetCC": None,
        }  # fmt: skip

    nulos = ["CCpraCueCon", "CCpraCC"]
    cabecera = {
        "empCodigo": m.emp_codigo, "CCpraTipoComprobante": tipo, "CCpraPtoVenta": pto, "CCpraNumero": None,
        "CCpraFechaEmision": emision, "CCpraFechaContabilizacion": emision, "CCpraPeriodoFiscal": m.periodo_fiscal_id,
        "CCpraConcepto": concepto, "CCpraMoneda": "PES", "CCpraTipoCambio": "1.000000", "CCpraCondFiscal": 5,
        "CCpraCliProvId": m.proveedor_id, "CCpraRzSocial": m.proveedor_rz, "CCpraTipoDoc": m.proveedor_tipo_doc,
        # NroDoc REAL: la API valida que corresponda al tipo de documento (CUIT = 11 dígitos).
        "CCpraNumeroDoc": m.proveedor_nro_doc, "CCpraProvin": m.proveedor_provincia_id, "CCpraCanje": False,
        "CCpraMonotComputable": True, **dict.fromkeys(nulos), "origenCod": "ORI", "CCpraCBU": None,
        "CCpraMonotOperacion": "C", "CCpraAduana": None, "CCpraDestino": None, "CCPraNroDespacho": None,
        "CCPraDigVerificador": None, "CCpraTipoImpo": None, "CCPraNIF": None, "CCpraRelacionTipo": None,
        "CCpraRelacionPtoVta": None, "CCpraRelacionNumero": None, "CCpraRelacionFecha": None,
        "CCpraRelacionImporte": None, "CCpraRelacionMoneda": None, "CCpraRelacionTipoCambio": None,
        "CCPraRelacionCUITPrestador": None, "CCPraRelacionNIFPrestador": None,
        "CCPraRelacionDenominacionPrestador": None, "CCpraCUITCorredor": None, "CCpraDenominacionCorredor": None,
        "CCpraIVAComision": None,
    }  # fmt: skip
    return {
        "cabecera": cabecera,
        "detalles": [
            detalle(m.mov_tipo_id_venta_neta, 12400.0 + jit1, 2.5),
            detalle(m.mov_tipo_id_iva_cinco, 565000.0 + jit2, 5.0),
        ],
    }


def _crear(user: UsuarioApi, nombre: str, variante: str, r: dict) -> int:
    fila = user.ctx.fila
    quien = f"{fila.usuario}@{fila.tenancy}" if fila.tenancy else fila.usuario
    body = cuerpo_comprobante(user.ctx.maestros, variante, quien)
    r.update({"tipo": body["cabecera"]["CCpraTipoComprobante"], "pto_venta": body["cabecera"]["CCpraPtoVenta"]})
    cid, motivo = con_sesion(user, api.crear_comprobante_compra, user, nombre, body)
    if cid is None:
        raise FallaTrabajo(f"{user.ctx.etiqueta} {nombre}: {motivo}")
    r["comprobante_id"] = cid
    logger.info("%s comprobante creado: id=%s", user.ctx.etiqueta, cid)
    return cid


# ─────────────── LITE ───────────────


class ComprobanteLite:
    def __init__(self, user: UsuarioApi):
        self.user = user

    def ejecutar(self):
        return ejecutar_ciclo(self.user, PREFIJO, N_FLUJO_LITE, self._ciclo, variante="lite")

    def _ciclo(self, r: dict) -> None:
        u, m = self.user, self.user.ctx.maestros
        fecha = hoy().strftime("%Y-%m-%d")
        # Lookups que la pantalla usa para armar el comprobante (como el navegador: no cortan el ciclo).
        navegar(u, "GET", f"{api.rutas.APP}/GdcLookups/GetAlicuotasVigentes?fechaComprobante={fecha}",
                "/LITE/Lookups/GetAlicuotasVigentes")  # fmt: skip
        navegar(u, "GET", f"{api.rutas.APP}/GdcClienteProveedor/Buscar?empCodigo={m.emp_codigo}"
                f"&tipoDoc={m.proveedor_tipo_doc}&nroDoc={m.proveedor_nro_doc}&periodoFiscalId={m.periodo_fiscal_id}"
                f"&clienteProveedorId={m.proveedor_id}", "/LITE/Lookups/GdcClienteProveedor_Buscar")  # fmt: skip
        navegar(u, "GET", f"{api.rutas.APP}/GdcLookups/GetClasificacionARCA?cpraVta=C",
                "/LITE/Lookups/GetClasificacionARCA")  # fmt: skip
        navegar(u, "POST", f"{api.rutas.MOVIMIENTO_TIPOS}?empCodigo={m.emp_codigo}",
                "/LITE/Lookups/getMovimientoTipoConsultaLookup_GRC",
                json={"page": 1, "limit": 10, "sort": {"field": "movimientoTipoDesc", "direction": "ASC"},
                      "filter": {"MovimientoTipoClase": ["GR"], "MovimientoTipoCpraVta": "C",
                                 "MovimientoTipoActivo": True}})  # fmt: skip

        cid = _crear(u, N_CREAR_LITE, "lite", r)
        errores = []
        for n in ("DETALLE_1", "DETALLE_2"):
            motivo = con_sesion(u, api.leer_comprobante_compra, u, f"/LITE/ComprobantesCompra/GetById_{n}", cid)
            if motivo:
                errores.append(motivo)
        if errores:
            raise FallaTrabajo(f"{u.ctx.etiqueta} {errores[0]}")


# ─────────────── COMPLETO ───────────────


class ComprobanteCompleto:
    def __init__(self, user: UsuarioApi):
        if user.ctx.fila.login != "plataforma" or user.settings.plataforma is None:
            raise FallaDatos(
                f"{user.ctx.etiqueta} el flujo completo navega la plataforma: la fila necesita login=plataforma "
                "y el ambiente la sección 'plataforma:'"
            )
        self.user = user

    def ejecutar(self):
        return ejecutar_ciclo(self.user, PREFIJO, N_FLUJO_COMPLETO, self._ciclo, variante="completo")

    def _valores(self) -> dict:
        u, m, plat = self.user, self.user.ctx.maestros, self.user.settings.plataforma
        return {
            "plataforma": plat.host_url, "portal": plat.portal_url, "front": plat.front_url,
            "back": u.settings.base_url, "token": u.ctx.token or "",
            "tenant_id": u.ctx.abp_tenant_id or u.ctx.fila.tenant_id, "user_id": u.ctx.user_id or "",
            "emp": m.emp_codigo, "periodo_id": m.periodo_fiscal_id, "periodo_cod": m.periodo_fiscal_cod,
            "prov_id": m.proveedor_id, "prov_tipo_doc": m.proveedor_tipo_doc, "prov_nro_doc": m.proveedor_nro_doc,
            "mov1": m.mov_tipo_id_venta_neta, "mov2": m.mov_tipo_id_iva_cinco, "fecha": hoy().strftime("%Y-%m-%d"),
        }  # fmt: skip

    def _navegar(self, lista: list[pasos.Paso], v: dict) -> None:
        for p in lista:
            cuerpo = p.cuerpo(v) if p.cuerpo else None
            navegar(self.user, p.metodo, p.url.format(**v), p.nombre.format(**v), json=cuerpo, headers=p.headers)

    def _ciclo(self, r: dict) -> None:
        u = self.user
        v = self._valores()
        self._navegar(pasos.ANTES, v)  # 1 a 102
        cid = _crear(u, N_CREAR_COMPLETO, "completo", r)  # 103
        self._navegar(pasos.DESPUES_GRILLA, v)  # 104 a 107
        # 108: página del detalle del comprobante recién creado (front)
        navegar(u, "GET", f"{v['front']}/dashboard/comprobantes/compras/detail/{cid}?mode=view&_rsc=4f3l6",
                f"/dashboard/comprobantes/compras/detail/{cid}", headers=_HEADERS_DETALLE)  # fmt: skip
        # 109: detalle por API
        motivo = con_sesion(u, api.leer_comprobante_compra, u, f"/api/service/ComprobantesCompra/{cid}", cid)
        self._navegar(pasos.FINAL, v)  # 110 a 113
        if motivo:
            raise FallaTrabajo(f"{u.ctx.etiqueta} {motivo}")


_HEADERS_DETALLE = {
    "RSC": "1",
    "Next-Url": "/dashboard/comprobantes/compras",
    "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22comprobantes%22%2C%7B%22children%22%3A%5B%22compras%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",  # noqa: E501
    "Accept": "*/*",
}
