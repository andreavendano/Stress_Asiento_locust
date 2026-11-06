"""Consultas de verificación de una corrida en la base del tenant (solo SELECT).

1. Por trabajo: asientos OK en nuc_AsientosOtrosModulos y comprobantes contabilizados con esos GUID
   (CCpraGUIDAsiento / CVtaGUIDAsiento). Es la cantidad REAL de comprobantes que procesó cada trabajo.
2. Trabajos con falla sin requestId (p. ej. timeout en generar): asientos "huérfanos" que el servidor
   pudo haber creado igual, buscados por empresa, tipo y período, y los comprobantes que contabilizaron.

Se usan de dos formas: escritas en verificacion.sql (para SSMS) y ejecutadas por bd.verificacion.

⚠ Ejecutarlas apenas termina la corrida: con reemplazar=true una corrida posterior sobre la misma
empresa / tipo / mes borra esos asientos y los recrea con GUID nuevos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

# tipoLote → (tabla de comprobantes, prefijo de columnas, leyenda del asiento)
TABLAS = {
    "COMPRAS": ("gdc_ComprobanteCompraCab", "CCpra", "Resumen Compras"),
    "VENTAS": ("gdc_ComprobanteVentaCab", "CVta", "Resumen Ventas"),
}
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class Consulta:
    tipo: str  # "trabajo" (1 fila) | "huerfanos" (lista de asientos) | "huerfanos_comprobantes" (1 fila)
    clave: str  # trabajo al que pertenece: clave_trabajo() = fila|inicio
    titulo: str
    sql: str
    tenant: str = ""  # tenantId del trabajo: la consulta va a la base de ese tenant


def _texto(v) -> str:
    return "'" + str(v or "").replace("'", "''") + "'"


def _entero(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return "NULL"


def _fecha(v) -> str:
    """Solo AAAA-MM-DD (lo que se interpola en el SQL nunca es texto libre)."""
    s = str(v or "")[:10]
    return _texto(s) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else "NULL"


def clave_trabajo(f: dict) -> str:
    """Identifica un trabajo dentro de la corrida (una fila puede tener varios trabajos sin cuota)."""
    return f"{f.get('fila')}|{f.get('inicio')}"


def _utc(inicio: str) -> str | None:
    """Hora local de la corrida (trabajos.csv) → UTC, como AsientoFechaCreacion en la base."""
    try:
        return datetime.fromisoformat(str(inicio)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def ultimos_por_fila(detalle: list[dict]) -> tuple[set[str], dict[str, str | None]]:
    """(claves de los últimos trabajos de cada fila, clave → inicio del siguiente trabajo de la misma fila).

    Con reemplazar=true cada trabajo borra los asientos del anterior de la misma fila: solo el último
    sigue en la base.
    """
    por_fila: dict[str, list[dict]] = {}
    for f in detalle:
        por_fila.setdefault(str(f.get("fila")), []).append(f)
    ultimos, siguiente = set(), {}
    for trabajos in por_fila.values():
        trabajos.sort(key=lambda f: str(f.get("inicio")))
        ultimos.add(clave_trabajo(trabajos[-1]))
        for actual, prox in zip(trabajos, [*trabajos[1:], None], strict=True):
            siguiente[clave_trabajo(actual)] = prox.get("inicio") if prox else None
    return ultimos, siguiente


def consultas(resumen: dict) -> list[Consulta]:
    tr = resumen.get("trabajos")
    if not tr:
        return []
    resultado = []
    ultimos, siguiente = ultimos_por_fila(tr["detalle"])
    for f in tr["detalle"]:
        tabla = TABLAS.get(str(f.get("tipo_lote") or "").upper())
        if tabla is None:
            continue
        nombre, prefijo, leyenda = tabla
        clave = clave_trabajo(f)
        tenant = str(f.get("tenant") or "")
        etiqueta = f"{f.get('usuario')} · E{f.get('empresa')} · {f.get('tipo_lote')}"
        if tenant:
            etiqueta = f"T{tenant} · {etiqueta}"
        ids = [i for i in str(f.get("ids_asientos") or "").split() if _GUID.match(i)]
        if ids and clave in ultimos:  # los anteriores de la misma fila ya fueron reemplazados
            lista = ", ".join(_texto(i) for i in ids)
            resultado.append(
                Consulta(
                    "trabajo",
                    clave,
                    f"{etiqueta} · {len(ids)} asientos · requestId {f.get('request_id')}",
                    f"SELECT {_texto(f.get('fila'))} AS fila, {_texto(f.get('usuario'))} AS usuario, "
                    f"{_entero(f.get('empresa'))} AS empresa, {_texto(f.get('tipo_lote'))} AS tipo, "
                    f"{_entero(f.get('asientos_total'))} AS asientos_enviados, "
                    f"{_entero(f.get('comprobantes_lote'))} AS comprobantes_esperados,\n"
                    f"       (SELECT COUNT(*) FROM nuc_AsientosOtrosModulos WHERE AsientosStatus = 'OK' "
                    f"AND AsientosID IN ({lista})) AS asientos_ok_control,\n"
                    f"       (SELECT COUNT(*) FROM {nombre} WHERE {prefijo}Contabilizado = 1 "
                    f"AND {prefijo}GUIDAsiento IN ({lista})) AS comprobantes_contabilizados",
                    tenant,
                )
            )
        elif f.get("resultado") != "OK" and not f.get("request_id"):
            # Ventana: desde el inicio de este trabajo hasta el inicio del siguiente de la misma fila (en UTC),
            # para no confundir con los asientos que creó un trabajo posterior.
            desde, hasta = _utc(f.get("inicio")), _utc(siguiente.get(clave) or "")
            ventana = (
                f"  AND AsientoFechaCreacion >= {_texto(desde)}"
                if desde
                else f"  AND AsientoFechaCreacion >= CAST({_fecha(f.get('inicio'))} AS date)"
            )
            if hasta:
                ventana += f" AND AsientoFechaCreacion < {_texto(hasta)}"
            filtro = (
                f"AsientosModulo = 'GDC' AND AsientosEmpresa = {_entero(f.get('empresa'))}\n"
                f"  AND AsientosFecha BETWEEN {_fecha(f.get('fecha_desde'))} AND {_fecha(f.get('fecha_hasta'))}\n"
                f"  AND AsientosLeyenda LIKE {_texto(leyenda + '%')}\n" + ventana
            )
            titulo = (
                f"{etiqueta} · {f.get('fecha_desde')} a {f.get('fecha_hasta')} · inicio {f.get('inicio')} · "
                f"{str(f.get('errores'))[:120]}"
            )
            resultado.append(
                Consulta(
                    "huerfanos",
                    clave,
                    titulo,
                    "SELECT AsientoFechaCreacion, AsientosEmpresa, AsientosEjercicio, AsientosTipo, AsientosFecha, "
                    "AsientosLeyenda, AsientosStatus, AsientosErrores, AsientosID\n"
                    f"FROM nuc_AsientosOtrosModulos\nWHERE {filtro}\nORDER BY AsientoFechaCreacion DESC, AsientosFecha",
                    tenant,
                )
            )
            resultado.append(
                Consulta(
                    "huerfanos_comprobantes",
                    clave,
                    f"{etiqueta} · comprobantes contabilizados por esos asientos",
                    f"SELECT COUNT(*) AS comprobantes_contabilizados FROM {nombre}\n"
                    f"WHERE {prefijo}Contabilizado = 1 AND {prefijo}GUIDAsiento IN (\n"
                    f"  SELECT AsientosID FROM nuc_AsientosOtrosModulos WHERE {filtro})",
                    tenant,
                )
            )
    return resultado


def generar_sql(resumen: dict) -> str | None:
    """Texto de verificacion.sql (para ejecutar a mano en SSMS)."""
    lista = consultas(resumen)
    if not resumen.get("trabajos"):
        return None
    lineas = [
        f"-- Verificación de la corrida {resumen['run_id']} ({resumen['escenario_desc']})",
        f"-- Ambiente {resumen['ambiente']} · {resumen['inicio']} → {resumen['fin'] or '—'}",
        "-- ⚠ Ejecutar apenas termina la corrida: con reemplazar=true, una corrida posterior sobre la misma",
        "--   empresa / tipo / mes reemplaza estos asientos (GUID nuevos) y los conteos darían 0.",
        "-- Las fechas de creación en la base están en UTC.",
        "-- Cada consulta va en la base del tenant de su trabajo (T<tenantId> en el título).",
        "",
    ]
    if not lista:
        lineas.append("-- (no hay trabajos de COMPRAS o VENTAS para verificar)")
    titulos = {
        "trabajo": "-- 1) Por trabajo: asientos OK en la tabla de control y comprobantes contabilizados con esos GUID",
        "huerfanos": "-- 2) Trabajos con falla y sin requestId: ¿el servidor creó los asientos igual?",
    }
    for c in lista:
        if c.tipo in titulos:
            lineas += [titulos.pop(c.tipo), ""]
        lineas += [f"-- {c.titulo}", c.sql + ";", ""]
    return "\n".join(lineas)
