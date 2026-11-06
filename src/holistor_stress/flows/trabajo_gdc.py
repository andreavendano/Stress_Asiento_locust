"""Un trabajo GDC de punta a punta: generar → seguir la cola → resultado → verificar → registrar.

Publica las métricas de negocio en las tablas de Locust:
- [E2E] GDC encolado→Finalizado, [E2E] GDC tiempo En Cola, [E2E] GDC tiempo de proceso
- [E2E] Trabajo completo (falla si algún asiento no queda OK o si alguna verificación no cierra)
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from holistor_stress.api import crear_asiento as api_crear
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core import metrics
from holistor_stress.core.context import id_asiento
from holistor_stress.core.errores import FallaPaso, SesionInvalidadaError
from holistor_stress.flows import verificacion
from holistor_stress.flows.gdc import generar_asiento_gdc
from holistor_stress.flows.seguimiento import esperar_finalizacion
from holistor_stress.flows.sesion import con_sesion
from holistor_stress.reporting.trabajos import ResultadoTrabajo

logger = logging.getLogger("holistor_stress")

N_E2E_TOTAL = "[E2E] GDC encolado→Finalizado"
N_E2E_COLA = "[E2E] GDC tiempo En Cola"
N_E2E_PROCESO = "[E2E] GDC tiempo de proceso"
N_E2E_TRABAJO = "[E2E] Trabajo completo"
TIPO_E2E = "E2E"

_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _sin_etiqueta(texto: str, etiqueta: str) -> str:
    return texto.removeprefix(etiqueta).strip()


def _mensaje_falla(etiqueta: str, errores: list[str]) -> str:
    """Mensaje para Locust: agrupa por tipo de error (sin GUIDs, que harían cada falla única)."""
    principal = _GUID.sub("<id>", errores[0])
    extra = f" (+{len(errores) - 1} más)" if len(errores) > 1 else ""
    return f"{etiqueta} {principal}{extra}"


def ejecutar_trabajo_gdc(user: UsuarioApi) -> ResultadoTrabajo:
    """Ejecuta un trabajo y lo registra. Solo propaga SesionInvalidadaError (el usuario debe detenerse)."""
    ctx, s, env = user.ctx, user.settings, user.environment
    fila, etq = ctx.fila, ctx.etiqueta
    r = ResultadoTrabajo(
        inicio=datetime.now().isoformat(timespec="seconds"),
        fila=fila.id,
        tenant=fila.tenant_id,
        usuario=fila.usuario,
        modulo=fila.modulo,
        empresa=fila.empresa,
        ejercicio=ctx.ejercicio.codigo,
        fecha_desde=ctx.periodo.fecha_desde[:10],
        fecha_hasta=ctx.periodo.fecha_hasta[:10],
        meses=len(ctx.periodo.meses),
        tipo_lote=(ctx.origen.tipo_lote or fila.tipo_lote or "") if ctx.origen else "",
        comprobantes_precheck=ctx.registros_precheck,
    )
    volumen = getattr(getattr(user, "rt", None), "volumen", None)
    if volumen is not None:
        r.comprobantes_lote = volumen.comprobantes(fila.empresa, r.tipo_lote or fila.tipo_lote, ctx.periodo.meses)
    t0 = time.perf_counter()
    sesion_perdida: SesionInvalidadaError | None = None
    try:
        t_generar = time.perf_counter()
        try:
            envio = con_sesion(user, generar_asiento_gdc, user)
        finally:  # también si falla (p. ej. timeout): es el dato que explica la falla
            r.s_generar = time.perf_counter() - t_generar
        r.request_id, r.asientos_total = envio.request_id, len(envio.asientos)

        prog = esperar_finalizacion(user, envio)
        r.estado_final, r.consultas_progreso = prog.estado, prog.consultas
        r.s_total, r.s_en_cola, r.s_proceso = prog.s_total, prog.s_en_cola, prog.s_proceso
        error_estado = None if prog.finalizado else f"{etq} la cola terminó en estado {prog.estado}"
        metrics.registrar(env, TIPO_E2E, N_E2E_TOTAL, prog.s_total * 1000, error=error_estado)
        if prog.s_en_cola is not None:
            metrics.registrar(env, TIPO_E2E, N_E2E_COLA, prog.s_en_cola * 1000)
        if prog.s_proceso is not None:
            metrics.registrar(env, TIPO_E2E, N_E2E_PROCESO, prog.s_proceso * 1000)
        if error_estado:
            r.errores.append(_sin_etiqueta(error_estado, etq))

        devueltos = (con_sesion(user, api_crear.resultado, user, envio.request_id) or {}).get("asientos") or []
        r.asientos_ok = verificacion.asientos_ok(devueltos)
        r.ids_asientos = [id_asiento(a) for a in devueltos]
        r.errores += verificacion.verificar_destino(list(envio.asientos), devueltos, fila.empresa, ctx.ejercicio.codigo)

        registro = getattr(getattr(user, "rt", None), "trabajos", None)
        if registro is not None and (repetidos := registro.ids_repetidos(fila.id, r.ids_asientos)):
            r.errores.append(f"IDs de asiento ya devueltos a otro trabajo: {', '.join(repetidos[:3])}")

        if s.flujo.verificar_fechas:
            r.errores += verificacion.verificar_fechas_asientos(user, envio)
        if s.flujo.verificar_control:
            control, errores_control = verificacion.consultar_control(user, envio)
            r.control = ", ".join(f"{k}={v}" for k, v in control.items() if v is not None)
            r.errores += errores_control
    except SesionInvalidadaError as e:
        sesion_perdida = e
        r.errores.append(_sin_etiqueta(str(e), etq))
    except FallaPaso as e:
        r.errores.append(_sin_etiqueta(str(e), etq))

    r.s_trabajo = time.perf_counter() - t0
    r.resultado = "OK" if r.ok else "FALLA"
    error = _mensaje_falla(etq, r.errores) if r.errores else None
    metrics.registrar(env, TIPO_E2E, N_E2E_TRABAJO, r.s_trabajo * 1000, error=error)
    if registro := getattr(getattr(user, "rt", None), "trabajos", None):
        registro.registrar(r)
    if r.ok:
        logger.info("%s OK · %d/%d asientos · %.1f s", etq, r.asientos_ok, r.asientos_total, r.s_total or 0)
    else:
        logger.warning("%s FALLA · %s", etq, " | ".join(r.errores))
    if sesion_perdida:
        raise sesion_perdida
    return r
