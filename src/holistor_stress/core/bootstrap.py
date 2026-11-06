"""Integración con Locust. Los locustfiles lo importan para registrar los listeners:

    from holistor_stress.core import bootstrap  # noqa: F401

- Agrega los argumentos --target-env, --load-profile, --permitir-produccion y --filtro-filas.
- En `init` carga configuración y datos, aplica la guardia de producción, fija el host y deja el
  runtime en `environment.holistor`. Si algo no es válido, termina el proceso con código 1 y un
  mensaje claro, antes de lanzar un solo request.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from locust import events

from holistor_stress.config import ConfigError
from holistor_stress.core.guardia import GuardiaProduccionError
from holistor_stress.core.runtime import HolistorRuntime, preparar_runtime, resumen
from holistor_stress.data.users_loader import DatosInvalidosError
from holistor_stress.reporting import informe, salida

logger = logging.getLogger("holistor_stress")


@events.init_command_line_parser.add_listener
def _agregar_argumentos(parser, **_kwargs):
    grupo = parser.add_argument_group("Holistor")
    grupo.add_argument(
        "--target-env",
        type=str,
        env_var="LOCUST_TARGET_ENV",
        default="qa",
        help="Ambiente: nombre de un archivo de environments/ (por defecto: qa)",
    )
    grupo.add_argument(
        "--load-profile",
        type=str,
        env_var="LOCUST_LOAD_PROFILE",
        default="",
        help="Perfil de etapas de profiles/ (stress, spike…)",
    )
    grupo.add_argument(
        "--permitir-produccion",
        action="store_true",
        env_var="LOCUST_PERMITIR_PRODUCCION",
        default=False,
        help="Permite correr contra un ambiente marcado como producción (crea asientos reales)",
    )
    grupo.add_argument(
        "--filtro-filas",
        type=str,
        env_var="LOCUST_FILTRO_FILAS",
        default="",
        help='Subconjunto de users.csv, por ejemplo "modulo=GDC,tipoLote=VENTAS|COMPRAS"',
    )
    grupo.add_argument(
        "--trabajos-por-usuario",
        type=int,
        env_var="LOCUST_TRABAJOS_POR_USUARIO",
        default=0,
        help="Trabajos de asiento por usuario virtual; al completarlos todos, la prueba termina (0 = sin límite)",
    )
    grupo.add_argument(
        "--carpeta-reportes",
        type=str,
        env_var="LOCUST_CARPETA_REPORTES",
        default="",
        help="Carpeta de trabajos.csv y run_info.json (por defecto reports/<run_id>)",
    )


def _usuarios_pedidos(environment) -> int | None:
    """Usuarios pedidos por CLI en modo headless sin shape (con shape o UI se controla en el pool)."""
    opts = environment.parsed_options
    if environment.shape_class is not None or not getattr(opts, "headless", False):
        return None
    return getattr(opts, "num_users", None)


_environment_actual = None  # el evento quit no recibe el environment


@events.init.add_listener
def _inicializar(environment, **_kwargs):
    global _environment_actual
    _environment_actual = environment
    opts = environment.parsed_options
    if opts is None:  # Locust usado como librería: el runtime se arma a mano.
        return
    try:
        rt = preparar_runtime(
            ambiente=opts.target_env,
            host=opts.host or None,
            filtro=opts.filtro_filas or None,
            usuarios_pedidos=_usuarios_pedidos(environment),
            permitir_produccion=bool(opts.permitir_produccion),
        )
    except (ConfigError, DatosInvalidosError, GuardiaProduccionError) as e:
        logger.error("No se puede iniciar la prueba.\n%s", e)
        sys.exit(1)

    rt.trabajos_por_usuario = max(0, opts.trabajos_por_usuario or 0)
    escenario = Path(str(opts.locustfile or "").split(",")[0]).stem or "escenario"
    usuarios = getattr(opts, "num_users", None)
    nombre = f"{rt.run.run_id}_{escenario}" + (f"_{usuarios}u" if usuarios else "")
    carpeta = Path(opts.carpeta_reportes) if opts.carpeta_reportes else rt.settings.ruta("reports") / nombre
    parametros = {
        "locustfile": opts.locustfile,
        "usuarios": getattr(opts, "num_users", None),
        "spawn_rate": getattr(opts, "spawn_rate", None),
        "duracion": getattr(opts, "run_time", None),
        "filtro_filas": opts.filtro_filas,
        "load_profile": opts.load_profile,
        "trabajos_por_usuario": rt.trabajos_por_usuario,
    }
    rt.preparar_reportes(rt.settings.ruta(carpeta), parametros)
    salida.agregar_log_archivo(rt.carpeta_reportes)
    if not getattr(opts, "html_file", None):
        opts.html_file = str(rt.carpeta_reportes / "locust_report.html")  # Locust lo lee al terminar
    rt.muestreador = salida.Muestreador(environment, rt.carpeta_reportes)

    environment.host = rt.base_url
    environment.holistor = rt
    for linea in resumen(rt):
        logger.info(linea)
    logger.info("Reportes de la corrida: %s", rt.carpeta_reportes)


@events.test_start.add_listener
def _iniciar_historial(environment, **_kwargs):
    rt = getattr(environment, "holistor", None)
    if rt is not None and getattr(rt, "muestreador", None) is not None:
        rt.inicio_monotonic = rt.inicio_monotonic or time.monotonic()
        rt.muestreador.iniciar()


@events.test_stop.add_listener
def _detener_historial(environment, **_kwargs):
    rt = getattr(environment, "holistor", None)
    if rt is not None and getattr(rt, "muestreador", None) is not None:
        rt.muestreador.detener()


def _verificar_en_bd(rt) -> None:
    """Verifica la corrida en la base apenas termina (antes de que otra corrida reemplace los asientos)."""
    bd = rt.settings.bd
    if not (bd.habilitada and bd.verificar_al_terminar) or rt.trabajos is None or not rt.trabajos.total:
        return
    from contextlib import ExitStack

    from holistor_stress.bd.conexion import BDError, ConfigBD
    from holistor_stress.bd.verificacion import abrir_conexiones, verificar_corrida

    try:
        with ExitStack() as pila:
            conexion, por_tenant = abrir_conexiones(ConfigBD.desde(rt.settings), bd.bases_por_tenant, pila)
            r = verificar_corrida(rt.carpeta_reportes, conexion, por_tenant)
        logger.info(
            "Verificación en la base (%s): %d trabajos consultados, %d con búsqueda de huérfanos, %d errores",
            r["base"],
            len(r["trabajos"]),
            len(r["huerfanos"]),
            len(r["errores"]),
        )
    except BDError as e:
        logger.warning("No se pudo verificar en la base (el informe se genera igual): %s", e)


@events.quit.add_listener
def _escribir_salida(exit_code=None, **_kwargs):
    """Al cerrar Locust: CSV nativos, run_info completo, resumen.md, reporte.html e índice de corridas."""
    environment = _environment_actual
    rt = getattr(environment, "holistor", None) if environment is not None else None
    if rt is None or rt.carpeta_reportes is None:
        return
    try:
        if getattr(rt, "muestreador", None) is not None:
            rt.muestreador.detener()
        salida.escribir_csv_locust(environment, rt.carpeta_reportes)
        salida.completar_run_info(rt.carpeta_reportes, exit_code, rt.inicio_monotonic)
        _verificar_en_bd(rt)
        informe.generar_corrida(rt.carpeta_reportes)
        indice = informe.generar_indice(rt.carpeta_reportes.parent)
        logger.info("Informe de la corrida: %s", rt.carpeta_reportes / "reporte.html")
        logger.info("Todas las corridas: %s", indice)
    except Exception:
        logger.exception("No se pudo generar el informe de la corrida (los CSV de Locust no se ven afectados)")


@events.quitting.add_listener
def _resumen_final(environment, **_kwargs):
    rt = getattr(environment, "holistor", None)
    if rt is None or rt.trabajos is None or not rt.trabajos.total:
        return
    t = rt.trabajos
    logger.info(
        "Trabajos de asiento: %d · OK %d · con falla %d · detalle en %s",
        t.total,
        t.total - t.fallidos,
        t.fallidos,
        t.archivo,
    )


def runtime_de(environment) -> HolistorRuntime:
    rt = getattr(environment, "holistor", None)
    if rt is None:
        raise RuntimeError("El runtime de Holistor no está inicializado: importar holistor_stress.core.bootstrap")
    return rt
