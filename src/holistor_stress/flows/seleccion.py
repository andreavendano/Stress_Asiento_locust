"""Selección de empresa, ejercicio, período y origen (pasos 01.2 a 01.4 de la colección de Postman).

Arriba están las reglas puras (sin red, con tests unitarios); abajo, los pasos que las usan.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from holistor_stress.api import ejercicio as api_ejercicio
from holistor_stress.api import origen as api_origen
from holistor_stress.api import periodo as api_periodo
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.context import Ejercicio, OrigenResuelto, PeriodoResuelto
from holistor_stress.core.errores import FallaDatos
from holistor_stress.data.fila import FilaCarga
from holistor_stress.data.periodo import RangoPeriodo

logger = logging.getLogger("holistor_stress")

# ─────────────────────────────── Reglas puras ───────────────────────────────


def _fecha(valor: Any) -> str:
    """'2026-01-01T00:00:00' → '2026-01-01'."""
    return str(valor or "")[:10]


def ejercicio_pedido(fila: FilaCarga, carpeta_plantillas: Path | None = None) -> int | None:
    """Ejercicio explícito: el de la fila o, en SYJ, el de la primera cabecera de su plantilla."""
    if fila.ejercicio is not None:
        return fila.ejercicio
    if fila.modulo == "SYJ" and fila.plantilla and carpeta_plantillas is not None:
        try:
            contenido = json.loads((carpeta_plantillas / fila.plantilla).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        cabeceras = contenido if isinstance(contenido, list) else (contenido or {}).get("Asiento_Cabecera") or []
        valor = cabeceras[0].get("Ejercicio") if cabeceras and isinstance(cabeceras[0], dict) else None
        try:
            return int(valor) if valor not in (None, "") else None
        except (TypeError, ValueError):
            return None
    return None


def elegir_ejercicio(data: Any, pedido: int | None, primer_mes: str | None) -> tuple[Ejercicio | None, str]:
    """Devuelve (ejercicio elegido o None, criterio usado) con el mismo orden que la colección:

    1. el ejercicio pedido (fila o plantilla SYJ);
    2. el que contiene el primer mes del período;
    3. con período TODOS, el preseleccionado por la pantalla (o el primero).
    """
    ejercicios = [e for e in ((data or {}).get("ejercicios") or []) if isinstance(e, dict)]
    elegido = None
    if pedido is not None:
        criterio = f"ejercicio {pedido}"
        elegido = next((e for e in ejercicios if _int(e.get("codigo")) == pedido), None)
    elif primer_mes:
        criterio = f"ejercicio que contiene {primer_mes}"
        dia = f"{primer_mes[:4]}-{primer_mes[4:]}-01"
        elegido = next(
            (e for e in ejercicios if _fecha(e.get("fechaDesde")) <= dia <= _fecha(e.get("fechaHasta"))), None
        )
    else:
        criterio = "ejercicio preseleccionado"
        preseleccionado = _int((data or {}).get("ejercicioSeleccionadoCodigo"))
        elegido = next((e for e in ejercicios if _int(e.get("codigo")) == preseleccionado), None) or (
            ejercicios[0] if ejercicios else None
        )
    if elegido is None:
        return None, criterio
    return Ejercicio(
        _int(elegido["codigo"]), _fecha(elegido.get("fechaDesde")), _fecha(elegido.get("fechaHasta"))
    ), criterio


def describir_ejercicios(data: Any) -> str:
    ejercicios = (data or {}).get("ejercicios") or []
    if not ejercicios:
        return "ninguno"
    return ", ".join(
        f"{e.get('codigo')} ({_fecha(e.get('fechaDesde'))} a {_fecha(e.get('fechaHasta'))})" for e in ejercicios
    )


def meses_del_periodo(data: Any, rango: RangoPeriodo) -> tuple[list[dict], list[str]]:
    """(meses del ejercicio que caen en el rango, meses pedidos que quedan fuera del ejercicio).

    Los períodos personalizados no son meses: se ignoran, igual que en la pantalla.
    """
    meses = sorted(
        (p for p in ((data or {}).get("periodos") or []) if isinstance(p, dict) and not p.get("personalizado")),
        key=lambda p: str(p.get("codigo")),
    )
    if rango.todos:
        return meses, []
    incluidos = [p for p in meses if rango.desde <= str(p.get("codigo")) <= rango.hasta]
    pedidos = rango.meses() or []
    codigos = {str(p.get("codigo")) for p in incluidos}
    fuera = [m for m in pedidos if m not in codigos] if incluidos else []
    return incluidos, fuera


def buscar_periodo_fiscal_id(data: Any, mes: str, empresa: int) -> int | None:
    """Busca en GetPeriodosFiscales el período cuyo código (sin separadores) es `mes` para la empresa."""
    if isinstance(data, dict):
        lista = data.get("items") or data.get("data") or []
    else:
        lista = data if isinstance(data, list) else []
    for p in lista:
        if not isinstance(p, dict):
            continue
        codigo = re.sub(r"\D", "", str(p.get("periodoFiscalCod") or p.get("fiscalPeriodCode") or ""))
        emp = p.get("empCodigo")
        if codigo == mes and (emp is None or _int(emp) == empresa):
            pid = p.get("periodoFiscalId") or p.get("PeriodoFiscalId") or p.get("id")
            if pid not in (None, ""):
                return _int(pid)
    return None


def origenes_candidatos(data: Any, origen_asiento_id: int | None) -> list[dict]:
    """Orígenes de comprobantes (esComprobante); si la fila fuerza uno, solo ese."""
    lista = [o for o in ((data or {}).get("origenes") or []) if isinstance(o, dict) and o.get("esComprobante")]
    if origen_asiento_id is not None:
        lista = [o for o in lista if _int(o.get("origenAsientoId")) == origen_asiento_id]
    return lista


def coincide_tipo_lote(data_tipos: Any, tipo_lote: str | None) -> bool:
    if not tipo_lote:
        return True
    return str((data_tipos or {}).get("tipoLote") or "").upper() == tipo_lote.upper()


def ids_tipos_comprobante(data_tipos: Any) -> tuple[int, ...]:
    tipos = (data_tipos or {}).get("tipos") or []
    return tuple(
        _int(t["tipoComprobanteId"]) for t in tipos if isinstance(t, dict) and t.get("tipoComprobanteId") is not None
    )


def _int(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────── Pasos ───────────────────────────────

_avisos_periodo_fiscal: set[str] = set()


def seleccionar_empresa_ejercicio(user: UsuarioApi) -> Ejercicio:
    """01.2 · acceso → la empresa está habilitada y tiene el ejercicio que corresponde a la fila."""
    fila, s = user.ctx.fila, user.settings
    pedido = ejercicio_pedido(fila, s.ruta(s.datos.plantillas_syj))
    elegido: dict[str, Ejercicio | None] = {}

    def validar(data: Any) -> str | None:
        ej, criterio = elegir_ejercicio(data, pedido, fila.rango.primer_mes)
        elegido["ej"] = ej
        if ej is None:
            return f"la empresa {fila.empresa} no tiene {criterio} · ejercicios: {describir_ejercicios(data)}"
        return None

    api_ejercicio.acceso(user, fila.empresa, validar=validar)
    user.ctx.ejercicio = elegido["ej"]
    return user.ctx.ejercicio


def seleccionar_periodo(user: UsuarioApi) -> PeriodoResuelto:
    """01.3 · periodos → meses del rango dentro del ejercicio; en GDC además el periodoFiscalId."""
    ctx = user.ctx
    fila, ej = ctx.fila, ctx.ejercicio
    if ej is None:
        raise RuntimeError("seleccionar_periodo requiere el ejercicio: ejecutar antes seleccionar_empresa_ejercicio")
    resultado: dict[str, Any] = {}

    def validar(data: Any) -> str | None:
        incluidos, fuera = meses_del_periodo(data, fila.rango)
        resultado.update(incluidos=incluidos, fuera=fuera)
        if incluidos:
            return None
        todos = [str(p.get("codigo")) for p in ((data or {}).get("periodos") or []) if isinstance(p, dict)]
        devueltos = f"{len(todos)} períodos" + (f" ({todos[0]} a {todos[-1]})" if todos else "")
        return (
            f"período {fila.periodo} fuera del ejercicio {ej.codigo} ({ej.desde} a {ej.hasta}) "
            f"· el servidor devolvió {devueltos}"
        )

    api_periodo.periodos(user, fila.empresa, ej.codigo, validar=validar)
    incluidos, fuera = resultado["incluidos"], resultado["fuera"]
    if fuera:
        logger.warning("%s meses fuera del ejercicio %s (no se generan): %s", ctx.etiqueta, ej.codigo, ", ".join(fuera))

    meses = tuple(str(p.get("codigo")) for p in incluidos)
    pf_id = resolver_periodo_fiscal_id(user, meses[0]) if fila.modulo == "GDC" else None
    ctx.periodo = PeriodoResuelto(
        meses=meses,
        fecha_desde=str(incluidos[0].get("desde")),
        fecha_hasta=str(incluidos[-1].get("hasta")),
        periodo_fiscal_id=pf_id,
        meses_fuera=tuple(fuera),
    )
    return ctx.periodo


def resolver_periodo_fiscal_id(user: UsuarioApi, mes: str) -> int:
    """GetPeriodosFiscales → periodoFiscalId; si no aparece, el de la fila o flujo.periodo_fiscal_id_defecto."""
    fila = user.ctx.fila
    encontrado = buscar_periodo_fiscal_id(api_periodo.periodos_fiscales(user, mes), mes, fila.empresa)
    if encontrado is not None:
        return encontrado
    respaldo = (
        fila.periodo_fiscal_id if fila.periodo_fiscal_id is not None else user.settings.flujo.periodo_fiscal_id_defecto
    )
    if respaldo is None:
        raise FallaDatos(
            f"{fila.etiqueta} GetPeriodosFiscales no encontró el período {mes} de la empresa {fila.empresa} "
            "y no hay respaldo (columna periodoFiscalId o flujo.periodo_fiscal_id_defecto)"
        )
    if fila.id not in _avisos_periodo_fiscal:  # una vez por fila, no en cada iteración
        _avisos_periodo_fiscal.add(fila.id)
        logger.warning("%s GetPeriodosFiscales no encontró %s: se usa periodoFiscalId %s", fila.etiqueta, mes, respaldo)
    return respaldo


def seleccionar_origen(user: UsuarioApi) -> OrigenResuelto:
    """01.4 · origenes + tipos-comprobante → el origen cuyo tipo de lote es el de la fila."""
    fila = user.ctx.fila
    candidatos = origenes_candidatos(api_origen.origenes(user), fila.origen_asiento_id)
    for o in candidatos:
        origen_id = _int(o.get("origenAsientoId"))
        tipos = api_origen.tipos_comprobante(user, origen_id)
        if coincide_tipo_lote(tipos, fila.tipo_lote):
            user.ctx.origen = OrigenResuelto(origen_id, (tipos or {}).get("tipoLote"), ids_tipos_comprobante(tipos))
            return user.ctx.origen
    buscado = fila.tipo_lote or f"origenAsientoId {fila.origen_asiento_id}"
    raise FallaDatos(
        f"{fila.etiqueta} no hay origen activo de comprobantes para {buscado} ({len(candidatos)} revisados)"
    )
