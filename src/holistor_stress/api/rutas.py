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
