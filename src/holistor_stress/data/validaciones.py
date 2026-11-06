"""Validaciones entre filas. Cada función devuelve una lista de errores (vacía = OK)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from holistor_stress.data.fila import FilaCarga


def validar_usuarios_unicos(filas: list[FilaCarga]) -> list[str]:
    """Sesión única: un mismo usuario logueado dos veces invalida el token del otro usuario virtual."""
    por_usuario: dict[tuple[int, str], list[str]] = defaultdict(list)
    for f in filas:
        por_usuario[(f.tenant_id, f.usuario.lower())].append(f.id)
    return [
        f"usuario '{usuario}' del tenant {tenant} repetido en las filas {', '.join(ids)}: "
        "con sesión única se invalidarían los tokens entre sí"
        for (tenant, usuario), ids in por_usuario.items()
        if len(ids) > 1
    ]


def _clave_reemplazo(f: FilaCarga) -> tuple:
    destino = f.tipo_lote or f"origen:{f.origen_asiento_id}"
    return (f.tenant_id, f.empresa, f.modulo, destino)


def validar_solapamientos(filas: list[FilaCarga]) -> list[str]:
    """Con reemplazar=true dos filas sobre la misma empresa/módulo/tipo y meses se borrarían los asientos.

    Solo GDC: en SYJ los meses y el tipo de asiento salen de la plantilla (se valida en la Fase 5).
    """
    grupos: dict[tuple, list[FilaCarga]] = defaultdict(list)
    for f in filas:
        if f.modulo == "GDC" and f.reemplazar_efectivo:
            grupos[_clave_reemplazo(f)].append(f)
    errores = []
    for (tenant, empresa, modulo, destino), grupo in grupos.items():
        for i, a in enumerate(grupo):
            for b in grupo[i + 1 :]:
                if a.rango.solapa(b.rango):
                    errores.append(
                        f"las filas {a.id} y {b.id} reemplazan los mismos asientos "
                        f"(tenant {tenant}, empresa {empresa}, {modulo} {destino}, "
                        f"períodos {a.periodo} y {b.periodo} se solapan)"
                    )
    return errores


def validar_plantillas_syj(filas: list[FilaCarga], carpeta: Path) -> list[str]:
    errores = []
    for f in filas:
        if f.modulo != "SYJ" or not f.plantilla:
            continue
        archivo = carpeta / f.plantilla
        if not archivo.is_file():
            errores.append(f"fila {f.id}: no existe la plantilla SYJ {archivo}")
            continue
        try:
            contenido = json.loads(archivo.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errores.append(f"fila {f.id}: la plantilla {archivo.name} no es JSON válido ({e})")
            continue
        cabeceras = contenido if isinstance(contenido, list) else (contenido or {}).get("Asiento_Cabecera")
        if not cabeceras:
            errores.append(f"fila {f.id}: la plantilla {archivo.name} no tiene Asiento_Cabecera")
    return errores


def validar_capacidad(filas: list[FilaCarga], usuarios_pedidos: int | None) -> list[str]:
    """Cada usuario virtual necesita una fila propia (sesión única)."""
    if usuarios_pedidos is None or usuarios_pedidos <= len(filas):
        return []
    return [
        f"hay {len(filas)} filas activas y se pidieron {usuarios_pedidos} usuarios: cada usuario virtual "
        "necesita un usuario propio (sesión única). Agregar filas o bajar --users."
    ]
