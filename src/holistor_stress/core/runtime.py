"""Arma todo lo necesario para una corrida: configuración + datos validados + pool + guardia.

Es independiente de Locust para poder usarlo también desde la CLI de verificación y desde los tests.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from holistor_stress import __version__
from holistor_stress.config import Settings, cargar_settings
from holistor_stress.core.guardia import verificar_ambiente
from holistor_stress.core.pool import PoolExclusivo
from holistor_stress.core.run_info import RunInfo, nueva_corrida
from holistor_stress.data.preparacion import DatosPreparados, preparar_datos
from holistor_stress.data.volumen import Volumen
from holistor_stress.reporting.trabajos import RegistroTrabajos


@dataclass
class HolistorRuntime:
    settings: Settings
    datos: DatosPreparados
    pool: PoolExclusivo
    run: RunInfo
    permitir_produccion: bool = False  # se vuelve a consultar si el host se cambia desde la UI de Locust
    trabajos_por_usuario: int = 0  # 0 = sin límite (hasta que termine la prueba)
    carpeta_reportes: Path | None = None
    trabajos: RegistroTrabajos | None = None
    usuarios_terminados: int = 0  # usuarios virtuales que completaron su cuota de trabajos
    muestreador: Any = None  # reporting.salida.Muestreador (historial.csv)
    volumen: Volumen | None = None  # comprobantes por empresa/mes (datos.volumen_csv)
    inicio_monotonic: float | None = None

    def preparar_reportes(self, carpeta: Path, parametros: dict | None = None) -> None:
        """Crea la carpeta de la corrida, run_info.json y el registro de trabajos.csv."""
        carpeta.mkdir(parents=True, exist_ok=True)
        info = {
            **self.run.como_dict(),
            "framework": __version__,
            "parametros": parametros or {},
            "thresholds": self.settings.thresholds.model_dump(),
            "flujo": self.settings.flujo.model_dump(),
        }
        (carpeta / "run_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        self.carpeta_reportes = carpeta
        self.trabajos = RegistroTrabajos(carpeta / "trabajos.csv")

    @property
    def base_url(self) -> str:
        return self.settings.base_url


def preparar_runtime(
    ambiente: str,
    host: str | None = None,
    filtro: str | None = None,
    usuarios_pedidos: int | None = None,
    permitir_produccion: bool = False,
    raiz: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> HolistorRuntime:
    """Lanza ConfigError, DatosInvalidosError o GuardiaProduccionError con mensajes listos para mostrar."""
    overrides = {"base_url": host} if host else None
    settings = cargar_settings(ambiente, raiz=raiz, environ=environ, overrides=overrides)
    # La guardia va antes que los datos: no tiene sentido validar un CSV para un destino prohibido.
    verificar_ambiente(settings, permitir_produccion=permitir_produccion)
    datos = preparar_datos(settings, filtro=filtro, usuarios_pedidos=usuarios_pedidos, environ=environ)
    return HolistorRuntime(
        settings=settings,
        datos=datos,
        pool=PoolExclusivo(datos.filas),
        run=nueva_corrida(settings.nombre, settings.base_url),
        permitir_produccion=permitir_produccion,
        volumen=_cargar_volumen(settings, datos),
    )


def _cargar_volumen(settings: Settings, datos: DatosPreparados) -> Volumen | None:
    """Opcional: si falta o no se puede leer, se avisa y trabajos.csv queda sin comprobantes_lote."""
    if not settings.datos.volumen_csv:
        return None
    ruta = settings.ruta(settings.datos.volumen_csv)
    try:
        return Volumen.desde_csv(ruta)
    except (OSError, KeyError, ValueError) as e:
        datos.advertencias.append(f"no se pudo leer el volumen de comprobantes {ruta}: {e}")
        return None


def resumen(rt: HolistorRuntime) -> list[str]:
    """Líneas legibles para logs y CLI (sin claves)."""
    filas = rt.datos.filas
    por_modulo: dict[str, int] = {}
    por_tenant: dict[int, int] = {}
    for f in filas:
        por_modulo[f.modulo] = por_modulo.get(f.modulo, 0) + 1
        por_tenant[f.tenant_id] = por_tenant.get(f.tenant_id, 0) + 1
    lineas = [
        f"Corrida {rt.run.run_id}",
        f"Ambiente: {rt.settings.nombre} · {rt.settings.base_url}",
        f"Filas activas: {len(filas)} (máximo de usuarios virtuales concurrentes)",
        "  por módulo: " + ", ".join(f"{m}={n}" for m, n in sorted(por_modulo.items())),
        "  por tenant: " + ", ".join(f"{t}={n}" for t, n in sorted(por_tenant.items())),
    ]
    if rt.datos.inactivas:
        lineas.append(f"Filas inactivas (activo=false): {rt.datos.inactivas}")
    if rt.datos.excluidas_por_filtro:
        lineas.append(f"Filas excluidas por --filtro-filas: {rt.datos.excluidas_por_filtro}")
    lineas += [f"ADVERTENCIA: {a}" for a in rt.datos.advertencias]
    return lineas
