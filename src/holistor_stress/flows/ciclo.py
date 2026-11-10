"""Ciclo de un escenario de comprobantes (antes `CicloMixin` de tasks/common/escenario.py).

1. arma `r` (datos del ciclo para el resumen) con usuario, empresa y período;
2. corre los pasos del escenario;
3. si un paso falla, el ciclo queda en ERROR con ese motivo (cualquier otra excepción también se informa);
4. registra la fila FLUJO "<PREFIJO> 00 …" en Locust, escribe "[<PREFIJO> RESUMEN]" en el log y una
   fila en ciclos.csv.

Ante una falla el usuario virtual sigue con el próximo ciclo; con `--trabajos-por-usuario 1` hace uno
solo (lo que antes era el escenario sin `_loop`). Solo una sesión invalidada detiene al usuario.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime

from holistor_stress.api.http import UsuarioApi
from holistor_stress.core import metrics
from holistor_stress.core.errores import FallaPaso, SesionInvalidadaError
from holistor_stress.reporting.ciclos import ResultadoCiclo

logger = logging.getLogger("holistor_stress")
# El resumen de cada ciclo se muestra siempre, aunque el nivel general sea WARNING.
resumen_logger = logging.getLogger("holistor_stress.resumen")
resumen_logger.setLevel(logging.INFO)

TIPO_VALIDACION = "VALIDACION"


def error_aparte(user: UsuarioApi, nombre: str, mensaje: str) -> None:
    """Error de negocio como fila propia en Failures, aunque el ciclo siga (líneas rechazadas, etc.)."""
    metrics.registrar(user.environment, TIPO_VALIDACION, nombre, 0, error=f"{user.ctx.etiqueta} {mensaje}")


def ejecutar_ciclo(
    user: UsuarioApi, prefijo: str, nombre_flujo: str, pasos: Callable[[dict], None], **datos
) -> ResultadoCiclo:
    """Corre `pasos(r)` y lo informa. Solo propaga SesionInvalidadaError (el usuario debe detenerse)."""
    ctx, fila = user.ctx, user.ctx.fila
    m = ctx.maestros
    quien = f"{fila.usuario}@{fila.tenancy}" if fila.tenancy else fila.usuario
    r = {"usuario": quien, "empresa": m.emp_codigo if m else fila.empresa,
         "periodo": m.periodo_fiscal_cod if m else fila.periodo, **datos}  # fmt: skip
    inicio = datetime.now().isoformat(timespec="seconds")
    t0 = time.perf_counter()
    error: str | None = None
    sesion_perdida: SesionInvalidadaError | None = None
    try:
        pasos(r)
    except SesionInvalidadaError as e:
        sesion_perdida = e
        error = str(e)
    except FallaPaso as e:
        error = str(e)
    except Exception as e:  # error inesperado (bug, conexión): también se informa
        logger.exception("%s [%s] error inesperado en el ciclo", ctx.etiqueta, prefijo)
        error = f"{ctx.etiqueta} error inesperado: {type(e).__name__}: {e}"

    ms = (time.perf_counter() - t0) * 1000
    metrics.registrar(user.environment, metrics.TIPO_FLUJO, nombre_flujo, ms, error=error)
    estado = "OK" if error is None else f"ERROR -> {error.removeprefix(ctx.etiqueta).strip()}"
    lineas = [f"    {k:<20}: {v}" for k, v in r.items()]
    resumen_logger.info("[%s RESUMEN] %s | duracion=%.1fs\n%s", prefijo, estado, ms / 1000, "\n".join(lineas))

    resultado = ResultadoCiclo(
        inicio=inicio,
        escenario=prefijo,
        fila=fila.id,
        tenant=fila.tenant_id,
        usuario=quien,
        empresa=r.get("empresa"),
        periodo=r.get("periodo"),
        resultado="OK" if error is None else "FALLA",
        segundos=ms / 1000,
        error="" if error is None else error.removeprefix(ctx.etiqueta).strip(),
        detalle={k: v for k, v in r.items() if k not in ("usuario", "empresa", "periodo")},
    )
    registro = getattr(getattr(user, "rt", None), "ciclos", None)
    if registro is not None:
        registro.registrar(resultado)
    if sesion_perdida:
        raise sesion_perdida
    return resultado
