"""Rutas y nombres de estadística de cada servicio. Ningún otro módulo escribe una URL."""

from __future__ import annotations

APP = "/api/services/app"
GDC = f"{APP}/GdcGenerarAsientos"

AUTHENTICATE = f"{APP}/Account/Authenticate"
ACCESO = f"{GDC}/acceso"
PERIODOS = f"{GDC}/periodos"
PERIODOS_FISCALES = f"{APP}/GdcPeriodo/GetPeriodosFiscales"
ORIGENES = f"{GDC}/origenes"
TIPOS_COMPROBANTE = f"{GDC}/tipos-comprobante"
PRECHECK_ESTRUCTURA = f"{GDC}/precheck-estructura"
GENERAR_ASIENTO = f"{GDC}/generar-asiento-comprobantes"
JOBS_ESTADO = f"{GDC}/jobs/estado"
RESULTADO_PROCESO = f"{GDC}/resultado-proceso"


def progreso(request_id: str) -> str:
    return f"{GDC}/crear-asiento/{request_id}/progreso"


def resultado(request_id: str) -> str:
    return f"{GDC}/crear-asiento/{request_id}"


# Nombre con el que cada servicio aparece en las tablas de Locust: "[Grupo] servicio".
N_AUTHENTICATE = "[Auth] Authenticate"
N_ACCESO = "[GDC] acceso"
N_PERIODOS = "[GDC] periodos"
N_PERIODOS_FISCALES = "[GDC] GetPeriodosFiscales"
N_ORIGENES = "[GDC] origenes"
N_TIPOS_COMPROBANTE = "[GDC] tipos-comprobante"
N_PRECHECK = "[GDC] precheck-estructura"
N_GENERAR = "[GDC] generar-asiento-comprobantes"
N_PROGRESO = "[CrearAsiento] progreso"
N_RESULTADO = "[CrearAsiento] resultado"
N_JOBS_ESTADO = "[Control] jobs/estado"
N_RESULTADO_PROCESO = "[Control] resultado-proceso"


# ─────────────── Login por la plataforma SaaS (filas con login=plataforma) ───────────────
# Se llaman sobre settings.plataforma.host_url (URL absoluta).
PLAT_IS_TENANT_AVAILABLE = f"{APP}/Account/IsTenantAvailable"
PLAT_TOKEN_AUTH = "/api/TokenAuth/Authenticate"
N_PLAT_CHECK_TENANT = "[Auth] Check_Tenant"
N_PLAT_AUTHENTICATE = "[Auth] TokenAuth/Authenticate"

# ─────────────── Datos maestros de los escenarios de comprobantes ───────────────
EMPRESAS_BY_TENANT = f"{APP}/Empresas/GetEmpresasByTenant"
PROVEEDOR_CONSULTA = f"{APP}/GdcLookups/GdcClienteProveedor/Consulta"
MOVIMIENTO_TIPOS = f"{APP}/GdcLookups/getMovimientoTipoConsultaLookup"
N_M_EMPRESAS = "[Maestros] GetEmpresasByTenant"
N_M_PERIODOS = "[Maestros] GetPeriodosFiscales"
N_M_PROVEEDOR = "[Maestros] GdcClienteProveedor/Consulta"
N_M_MOVTIPOS = "[Maestros] getMovimientoTipoConsultaLookup"

# ─────────────── Comprobantes de compra (grilla compartida por importación y modificación) ───────────────
GRILLA_COMPRAS = f"{APP}/GdcComprobanteCompra/getGrid"
COMPROBANTES_COMPRA = "/api/service/ComprobantesCompra"  # sin "s/app": así lo expone el back

# ─────────────── Importación de comprobantes de compra ───────────────
IMPO_ORIGENES = f"{APP}/GdcImpoOrigen/GetListForImport"
IMPO_ESTADO_COMPRAS = f"{APP}/GdcImpoArchivo/Importaciones/EstadoCompras"
IMPO_SELECT_FILE = f"{APP}/GdcImpoArchivo/SelectFile"
IMPO_VALIDATE_PRELIMINARY = f"{APP}/GdcImpoArchivo/ValidatePreliminary"
IMPO_INCORPORAR = f"{APP}/GdcImpoArchivo/Incorporar"
IMPO_ESTADO_ARCHIVO = f"{APP}/GdcImpoArchivo/GetEstadoArchivo"
IMPO_SUMMARY = f"{APP}/GdcImpoArchivo/GetSummaryImport"
IMPO_LINEAS = f"{APP}/GdcImpoArchivo/GetListComprobantes"
IMPO_INICIAR = f"{APP}/GdcImpoArchivo/ImportacionDefinitiva/Iniciar"
IMPO_VALIDAR_DEFINITIVOS = f"{APP}/GdcImpoArchivo/importacion/validar-definitivos"
IMPO_CUOTA = f"{APP}/GdcImpoArchivo/CheckQuota"
IMPO_START = f"{APP}/GdcImpoArchivo/ImportacionDefinitiva/Start"
IMPO_STREAM_JOB = "/api/gdc/importacion-definitiva-status-stream"  # en settings.plataforma.front_url

# ─────────────── Modificación masiva de cabecera ───────────────
PERIODO_PROTEGIDO = f"{APP}/GdcPeriodoFiscal/protegido"
MODIF_SELECCION_PROTEGIDA = f"{COMPROBANTES_COMPRA}/periodo-protegido"
MODIF_CATALOGO = f"{COMPROBANTES_COMPRA}/modificacion-masiva"  # + /condiciones-iva | /provincias
MODIF_CABECERA = f"{COMPROBANTES_COMPRA}/modificacion-masiva/cabecera"
