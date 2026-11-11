"""Servicios de la pantalla Importar de Gestor de Comprobantes (importación de comprobantes de compra).

Los nombres de cada request son los pasos "IMPO NN …" del proyecto original, para comparar reportes.
"""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import urlparse

import gevent

from holistor_stress.api import rutas
from holistor_stress.api.comprobantes import gdc
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.errores import FallaTrabajo

logger = logging.getLogger("holistor_stress")

N_ORIGEN = "IMPO 01 Origen de importacion"
N_EMPRESA_LIBRE = "IMPO 02 Empresa libre"
N_ANTES = "IMPO 03 Comprobantes antes"
N_SUBIR = "IMPO 04 Subir archivo"
N_VALIDACION = "IMPO 05 Validacion preliminar"
N_INCORPORAR = "IMPO 06 Incorporar archivo"
N_PROCESAMIENTO = "IMPO 07 Procesamiento del archivo"
N_RESUMEN = "IMPO 08 Resumen del archivo"
N_LINEAS = "IMPO 09 Lineas del archivo"
N_INICIAR = "IMPO 10 Iniciar importacion"
N_VALIDAR_DEF = "IMPO 11 Validar definitivos"
N_CUOTA = "IMPO 12 Cuota"
N_LANZAR = "IMPO 13 Lanzar importacion"
N_JOB = "IMPO 14 Seguimiento del job"
N_DESPUES = "IMPO 15 Comprobantes despues"


def origenes(user: UsuarioApi, emp: int, compra_venta: str, comp_cert: str) -> dict:
    return gdc(user, "POST", rutas.IMPO_ORIGENES, N_ORIGEN, json={
        "forSeleccionOrigen": True, "empCodigo": emp, "page": 1, "limit": 100,
        "sort": {"field": "Descripcion", "direction": "ASC"}, "search": "",
        "filter": {"CompraVenta": compra_venta, "ComprobanteCertificado": comp_cert, "Activo": True,
                   "OrigenImpo": True},
    })  # fmt: skip


def estado_compras(user: UsuarioApi, emp: int, periodo_id: int) -> dict:
    return gdc(user, "GET", rutas.IMPO_ESTADO_COMPRAS, N_EMPRESA_LIBRE,
               params={"empCodigo": emp, "periodoFiscalId": periodo_id})  # fmt: skip


def select_file(user: UsuarioApi, body: bytes, boundary: str) -> dict:
    return gdc(user, "POST", rutas.IMPO_SELECT_FILE, N_SUBIR, data=body,
               headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})  # fmt: skip


def validate_preliminary(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.IMPO_VALIDATE_PRELIMINARY, N_VALIDACION, json=body,
               validar=lambda j: None if j.get("canProceed") is True
               else f"se esperaba canProceed=True y vino {j.get('canProceed')!r}: {json.dumps(j)[:200]}")  # fmt: skip


def incorporar(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.IMPO_INCORPORAR, N_INCORPORAR, json=body)


def estado_archivo(user: UsuarioApi, id_archivo: int, emp: int) -> dict:
    body = {"idArchivo": id_archivo, "empCodigo": emp}
    return gdc(user, "POST", rutas.IMPO_ESTADO_ARCHIVO, N_PROCESAMIENTO, json=body)


def resumen_archivo(user: UsuarioApi, id_archivo: int, emp: int) -> dict:
    return gdc(user, "POST", rutas.IMPO_SUMMARY, N_RESUMEN, json={"idArchivo": id_archivo, "empCodigo": emp})


def lineas_archivo(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.IMPO_LINEAS, N_LINEAS, json=body)


def iniciar(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.IMPO_INICIAR, N_INICIAR, json=body)


def validar_definitivos(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.IMPO_VALIDAR_DEFINITIVOS, N_VALIDAR_DEF, json=body)


def cuota(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.IMPO_CUOTA, N_CUOTA, json=body)


def lanzar(user: UsuarioApi, body: dict) -> dict:
    return gdc(user, "POST", rutas.IMPO_START, N_LANZAR, json=body)


def seguir_job(user: UsuarioApi, job_id: str, timeout_s: float, intervalo_s: float) -> dict | None:
    """Lee el stream de estado del job (el mismo que usa la pantalla) hasta que termina o vence `timeout_s`.

    El front autentica el stream con la cookie `auth_token` (el token del usuario). Devuelve el último estado
    leído (None si no llegó ninguno). Si el stream no responde 200, el paso falla (FallaTrabajo).
    """
    front = user.settings.plataforma.front_url
    etq = user.ctx.etiqueta
    user.client.cookies.set("auth_token", user.ctx.token or "", domain=urlparse(front).hostname)
    # Como en el original (headers de sesión globales), también viajan el token y el tenant.
    cabeceras = {"Accept": "text/event-stream", "Authorization": f"Bearer {user.ctx.token or ''}"}
    if getattr(user.ctx, "abp_tenant_id", None):
        cabeceras["Abp.TenantId"] = str(user.ctx.abp_tenant_id)
    limite = time.time() + timeout_s
    ultimo: dict = {}
    while time.time() < limite:
        with user.client.get(
            f"{front}{rutas.IMPO_STREAM_JOB}",
            params={"jobId": job_id},
            headers=cabeceras,
            name=N_JOB,
            stream=True,
            catch_response=True,
            timeout=(10, 60),
        ) as r:
            if r.status_code != 200:
                detalle = (f"sin respuesta del servidor: {r.error!r}" if not r.status_code
                           else f"HTTP {r.status_code}: {r.text[:300]}")  # fmt: skip
                r.failure(f"{etq} {detalle}")
                raise FallaTrabajo(f"{etq} {N_JOB}: no se pudo leer el estado del job ({detalle})")
            r.encoding = "utf-8"
            r.success()
            try:
                for linea in r.iter_lines(decode_unicode=True):
                    # El límite se controla en CADA línea: los keepalive (": ping") no traen 'data:'
                    # y no deben estirar la espera.
                    if time.time() > limite:
                        break
                    if not linea or not linea.startswith("data:"):
                        continue
                    ultimo = json.loads(linea[5:]).get("data") or {}
                    if ultimo.get("finishedAt"):
                        break
            except Exception as e:  # corte del stream: se reconecta
                logger.warning("%s stream del job interrumpido (%s); reconectando", etq, type(e).__name__)
        if ultimo.get("finishedAt"):
            break
        gevent.sleep(intervalo_s)
    return ultimo or None
