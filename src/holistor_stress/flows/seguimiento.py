"""Seguimiento de la cola de Crear Asiento hasta Finalizado o Error (paso 01.7).

Mide, con la resolución del intervalo de polling:
- encolado → Finalizado: desde el 202 de generar hasta la consulta que ve el estado final;
- tiempo En Cola: desde el 202 hasta la primera consulta con un estado distinto de En Cola;
- tiempo de proceso: desde la primera consulta En Proceso (o la salida de la cola) hasta el final.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from holistor_stress.api import control as api_control
from holistor_stress.api import crear_asiento as api_crear
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.context import Envio
from holistor_stress.core.errores import FallaHttp, FallaTrabajo
from holistor_stress.flows.sesion import con_sesion

FINALIZADO, ERROR, EN_COLA, EN_PROCESO = "finalizado", "error", "encola", "enproceso"
# Errores HTTP seguidos tolerados durante el polling (bajo stress un 5xx aislado no invalida el trabajo).
ERRORES_POLLING_MAX = 3


def normalizar_estado(estado: Any) -> str:
    """'En Cola' → 'encola', 'Finalizado' → 'finalizado'."""
    return "".join(str(estado or "").split()).lower()


@dataclass
class Progreso:
    estado: str  # tal como lo devolvió el servidor en la última consulta
    consultas: int
    s_total: float
    s_en_cola: float | None
    s_proceso: float | None
    ultimo: Any = None

    @property
    def finalizado(self) -> bool:
        return normalizar_estado(self.estado) == FINALIZADO


def esperar_finalizacion(
    user: UsuarioApi,
    envio: Envio,
    reloj: Callable[[], float] = time.perf_counter,
    dormir: Callable[[float], None] = time.sleep,  # Locust parchea time.sleep con gevent: no bloquea a otros
) -> Progreso:
    """Consulta cada `flujo.polling.intervalo_s` hasta Finalizado / Error o `timeout_s`.

    Lanza FallaTrabajo ante timeout, requestId perdido (404) o errores HTTP persistentes.
    """
    s, etq = user.settings, user.ctx.etiqueta
    pol, por_jobs = s.flujo.polling, s.flujo.seguimiento == "jobs_estado"
    consultas = errores_seguidos = 0
    fin_cola = inicio_proceso = None
    ultimo_estado: Any = None

    while True:
        try:
            if por_jobs:
                data = con_sesion(user, api_control.jobs_estado, user, envio.claves())
            else:
                data = con_sesion(user, api_crear.progreso, user, envio.request_id)
            errores_seguidos = 0
        except FallaHttp as e:
            if e.status == 404:
                raise FallaTrabajo(
                    f"{etq} requestId perdido (404 en progreso): ¿se reinició el servidor o pasaron 30 min? "
                    f"· {envio.request_id}"
                ) from e
            errores_seguidos += 1
            if errores_seguidos >= ERRORES_POLLING_MAX:
                raise FallaTrabajo(f"{etq} seguimiento abandonado tras {errores_seguidos} errores seguidos: {e}") from e
            data = None

        ahora = reloj()
        if data is not None:
            consultas += 1
            ultimo_estado = _estado_jobs(data) if por_jobs else (data or {}).get("estado")
            estado = normalizar_estado(ultimo_estado)
            if fin_cola is None and estado and estado != EN_COLA:
                fin_cola = ahora
            if inicio_proceso is None and estado == EN_PROCESO:
                inicio_proceso = ahora
            if estado in (FINALIZADO, ERROR):
                desde_proceso = inicio_proceso or fin_cola or ahora
                return Progreso(
                    estado=str(ultimo_estado),
                    consultas=consultas,
                    s_total=ahora - envio.encolado_en,
                    s_en_cola=None if por_jobs or fin_cola is None else fin_cola - envio.encolado_en,
                    s_proceso=None if por_jobs else ahora - desde_proceso,
                    ultimo=data,
                )

        if ahora - envio.encolado_en >= pol.timeout_s:
            raise FallaTrabajo(
                f"{etq} no terminó en {pol.timeout_s:g} s: último estado {ultimo_estado!r} tras {consultas} consultas"
            )
        dormir(pol.intervalo_s)


def _estado_jobs(data: Any) -> str:
    """jobs/estado no informa En Cola / En Proceso: se deriva de pendientes y rechazados."""
    d = data or {}
    if int(d.get("pendientes") or 0) > 0 or not d.get("total"):
        return "En Proceso"
    return "Error" if int(d.get("rechazados") or 0) > 0 else "Finalizado"
