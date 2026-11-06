"""Pasos propios de GDC: contexto del armado, precheck y generar asiento."""

from __future__ import annotations

import calendar
import time
from typing import Any, Literal

from holistor_stress.api import gdc as api_gdc
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.context import ContextoAsiento, Envio
from holistor_stress.core.errores import FallaDatos


def hasta_primer_mes(fecha_desde: str, fecha_hasta: str) -> str:
    """Último día del mes de `fecha_desde`, con la parte horaria de `fecha_hasta` (como la colección).

    '2026-01-01T00:00:00', '2026-06-30T00:00:00' → '2026-01-31T00:00:00'.
    """
    if fecha_desde[:7] == fecha_hasta[:7]:
        return fecha_hasta
    anio, mes = int(fecha_desde[:4]), int(fecha_desde[5:7])
    ultimo = calendar.monthrange(anio, mes)[1]
    return f"{fecha_desde[:8]}{ultimo:02d}{fecha_hasta[10:]}"


def cuerpo_contexto(ctx: ContextoAsiento, fecha_hasta: str | None = None, reemplazar: bool = False) -> dict[str, Any]:
    """Contexto común del precheck y de generar-asiento-comprobantes."""
    if not ctx.listo:
        raise RuntimeError(f"{ctx.etiqueta} contexto incompleto: preparar el contexto antes de armar el cuerpo")
    return {
        "empCodigo": ctx.fila.empresa,
        "origenAsientoId": ctx.origen.origen_asiento_id,
        "ejCodigo": ctx.ejercicio.codigo,
        "periodoFiscalId": ctx.periodo.periodo_fiscal_id,
        "fechaDesde": ctx.periodo.fecha_desde,
        "fechaHasta": fecha_hasta or ctx.periodo.fecha_hasta,
        "comprobantesAIncluir": ctx.fila.comprobantes_a_incluir,
        "tipoComprobanteIds": list(ctx.origen.tipo_comprobante_ids),
        "reemplazar": reemplazar,
    }


def generar_asiento_gdc(user: UsuarioApi) -> Envio:
    """01.5 · Encola el asiento con el contexto resuelto. ⚠ Crea asientos (y con reemplazar borra los previos)."""
    ctx = user.ctx
    body = cuerpo_contexto(ctx, reemplazar=bool(ctx.fila.reemplazar_efectivo))
    data = api_gdc.generar_asiento_comprobantes(user, body)
    return Envio(request_id=data["requestId"], asientos=tuple(data["asientos"]), encolado_en=time.perf_counter())


def _contar_registros(data: Any) -> int:
    registros = (data or {}).get("registros") if isinstance(data, dict) else None
    return len(registros) if isinstance(registros, list) else 0


def precheck(user: UsuarioApi, alcance: Literal["primer_mes", "completo"] = "primer_mes") -> int:
    """Confirma que el lote tiene comprobantes (R4: la respuesta trae TODO el lote, ~2,8 KB c/u).

    `primer_mes` consulta solo el primer mes y pasa al rango completo únicamente si ese mes está vacío.
    """
    ctx = user.ctx
    desde, hasta = ctx.periodo.fecha_desde, ctx.periodo.fecha_hasta
    hasta_consulta = hasta if alcance == "completo" else hasta_primer_mes(desde, hasta)
    registros = _contar_registros(api_gdc.precheck_estructura(user, cuerpo_contexto(ctx, hasta_consulta)))
    if not registros and hasta_consulta != hasta:
        registros = _contar_registros(api_gdc.precheck_estructura(user, cuerpo_contexto(ctx, hasta)))
    ctx.registros_precheck = registros
    if not registros:
        raise FallaDatos(
            f"{ctx.etiqueta} lote sin comprobantes para generar ({ctx.origen.tipo_lote}, {desde[:10]} a {hasta[:10]})"
        )
    return registros
