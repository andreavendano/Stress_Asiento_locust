"""Orquesta carga + filtros + validaciones. Lo usan el bootstrap de Locust y la CLI de verificación."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from holistor_stress.config.settings import Settings
from holistor_stress.data import validaciones as v
from holistor_stress.data.fila import FilaCarga
from holistor_stress.data.filtros import aplicar_filtro, parsear_filtro
from holistor_stress.data.users_loader import DatosInvalidosError, cargar_filas


@dataclass
class DatosPreparados:
    filas: list[FilaCarga]
    inactivas: int = 0
    excluidas_por_modulo: int = 0
    excluidas_por_escenario: int = 0  # filas de otros módulos que este locustfile no usa
    excluidas_por_filtro: int = 0
    advertencias: list[str] = field(default_factory=list)


def preparar_datos(
    settings: Settings,
    filtro: str | None = None,
    usuarios_pedidos: int | None = None,
    environ: Mapping[str, str] | None = None,
    modulos: Iterable[str] | None = None,
) -> DatosPreparados:
    """`modulos`: solo las filas de esos módulos (cada locustfile declara los suyos). None = todas."""
    environ = os.environ if environ is None else environ
    var_clave = settings.datos.clave_env_var
    clave_defecto = environ.get(var_clave) if var_clave else None

    carga = cargar_filas(settings.ruta(settings.datos.users_csv), clave_defecto, var_clave)
    advertencias = list(carga.advertencias)

    habilitadas = [f for f in carga.filas if settings.modulos.habilitado(f.modulo)]
    excluidas_modulo = len(carga.filas) - len(habilitadas)
    if excluidas_modulo:
        deshabilitados = sorted({f.modulo for f in carga.filas} - {f.modulo for f in habilitadas})
        advertencias.append(
            f"{excluidas_modulo} filas excluidas: módulo deshabilitado en el ambiente ({', '.join(deshabilitados)})"
        )

    del_escenario = habilitadas
    if modulos is not None:
        modulos = {m.upper() for m in modulos}
        del_escenario = [f for f in habilitadas if f.modulo in modulos]

    try:
        filas = aplicar_filtro(del_escenario, parsear_filtro(filtro))
    except ValueError as e:
        raise DatosInvalidosError([f"--filtro-filas: {e}"]) from e

    # Sesión única: en una corrida no se puede repetir un usuario. Sin escenario (CLI de verificación) se
    # valida por módulo, porque cada módulo se corre con su propio locustfile.
    grupos: list[list[FilaCarga]] = [filas]
    if modulos is None:
        por_modulo: dict[str, list[FilaCarga]] = defaultdict(list)
        for f in filas:
            por_modulo[f.modulo].append(f)
        grupos = list(por_modulo.values())
    errores = [
        *(e for g in grupos for e in v.validar_usuarios_unicos(g)),
        *v.validar_solapamientos(filas),
        *v.validar_plantillas_syj(filas, settings.ruta(settings.datos.plantillas_syj)),
        *v.validar_empresa_unica_importacion(filas),
        *v.validar_login_plataforma(filas, settings.plataforma is not None),
    ]
    if not filas:
        errores.append("no quedan filas activas para ejecutar (revisar activo, módulos habilitados y filtro)")
    errores += v.validar_capacidad(filas, usuarios_pedidos)
    if errores:
        raise DatosInvalidosError(errores)

    return DatosPreparados(
        filas=filas,
        inactivas=carga.inactivas,
        excluidas_por_modulo=excluidas_modulo,
        excluidas_por_escenario=len(habilitadas) - len(del_escenario),
        excluidas_por_filtro=len(del_escenario) - len(filas),
        advertencias=advertencias,
    )
