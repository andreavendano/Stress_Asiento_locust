"""Servicios propios de GDC: precheck y generar asiento."""

from __future__ import annotations

from typing import Any

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, llamar
from holistor_stress.core.errores import FallaTrabajo


def _encolado(data: Any) -> str | None:
    if not isinstance(data, dict) or not isinstance(data.get("requestId"), str) or not data["requestId"]:
        return "generar no devolvió requestId"
    if not isinstance(data.get("asientos"), list) or not data["asientos"]:
        return "generar no devolvió asientos"
    return None


def generar_asiento_comprobantes(user: UsuarioApi, contexto: dict[str, Any]) -> Any:
    """POST generar-asiento-comprobantes → 202 {requestId, asientos[]: empresa, ejercicio, idAsiento}.

    ⚠ CREA ASIENTOS. Con reemplazar=true borra y recrea los del mismo mes, tipo y módulo.
    """
    return llamar(
        user,
        "POST",
        rutas.GENERAR_ASIENTO,
        rutas.N_GENERAR,
        json=contexto,
        esperado=(202,),
        validar=_encolado,
        error_validacion=FallaTrabajo,
    ).data


def precheck_estructura(user: UsuarioApi, contexto: dict[str, Any]) -> Any:
    """POST precheck-estructura → {registros[]}. ⚠ Respuesta pesada: ~2,8 KB por comprobante."""
    return llamar(user, "POST", rutas.PRECHECK_ESTRUCTURA, rutas.N_PRECHECK, json=contexto).data
