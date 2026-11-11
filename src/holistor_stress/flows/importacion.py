"""Importación de comprobantes de compra (antes tasks/gdc_importacion_lite.py).

Cada ciclo hace lo mismo que una persona en la pantalla Importar:
1. arma un CSV de comprobantes de compra (formato Portal IVA de ARCA), 2. lo sube y lo valida,
3. lanza la importación definitiva, 4. espera a que termine y 5. verifica que se crearon los comprobantes.

Pasos (nombre en Locust):
    IMPO 01 Origen de importacion      el origen por código (importacion.origen_codigo)
    IMPO 02 Empresa libre              espera que la empresa no tenga otra importación en curso
    IMPO 03 Comprobantes antes         cuenta los comprobantes del período (para el paso 15)
    IMPO 04 Subir archivo              SelectFile: sube el CSV generado
    IMPO 05 Validacion preliminar      estructura, nombre y encabezado del archivo
    IMPO 06 Incorporar archivo         el backend registra el archivo (idArchivo)
    IMPO 07 Procesamiento del archivo  espera que se procesen todas las líneas
    IMPO 08 Resumen del archivo        líneas OK / con advertencia / con error
    IMPO 09 Lineas del archivo         SOLO las líneas de ESTE archivo (filtro idArchivo)
    IMPO 10 Iniciar importacion        ImportacionDefinitiva/Iniciar
    IMPO 11 Validar definitivos        validación final
    IMPO 12 Cuota                      cuota de comprobantes del tenant
    IMPO 13 Lanzar importacion         ImportacionDefinitiva/Start (jobId)
    IMPO 14 Seguimiento del job        stream de estado del job hasta que termina
    IMPO 15 Comprobantes despues       se crearon los comprobantes aceptados
    IMPO 00 Importacion completa       el ciclo entero (FLUJO); ERROR si falla cualquier paso
"""

from __future__ import annotations

import csv
import io
import json
import logging
import random
import time
import uuid

import gevent

from holistor_stress.api import importacion as api
from holistor_stress.api.comprobantes import grilla_compras
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.errores import FallaDatos, FallaTrabajo
from holistor_stress.flows.ciclo import ejecutar_ciclo, error_aparte
from holistor_stress.flows.sesion import con_sesion

logger = logging.getLogger("holistor_stress")

PREFIJO = "IMPO"
N_FLUJO = "IMPO 00 Importacion completa (punta a punta)"

# Definición del escenario (no son datos de prueba): importación de COMPRAS, tipo comprobantes.
COMPRA_VENTA = "C"
COMPROBANTE_CERTIFICADO = "COMP"

# Tabla estándar de ARCA (AFIP): abreviatura de tipo de documento → código (texto del CSV).
TIPO_DOC_AFIP = {"CUIT": "80", "CUIL": "86", "CDI": "87", "DNI": "96", "LE": "89", "LC": "90", "PAS": "94", "CI": "92"}

# Columnas del formato Portal IVA que completa el escenario (se ubican por NOMBRE en la plantilla).
COL_FECHA = "Fecha de Emisión"
COL_TIPO_COMP = "Tipo de Comprobante"
COL_PTO_VENTA = "Punto de Venta"
COL_NUMERO = "Número de Comprobante"
COL_TIPO_DOC = "Tipo Doc. Vendedor"
COL_NRO_DOC = "Nro. Doc. Vendedor"
COL_DENOMINACION = "Denominación Vendedor"
COL_TOTAL = "Importe Total"
COL_MONEDA = "Moneda Original"
COL_TIPO_CAMBIO = "Tipo de Cambio"
COL_NETO_IVA_0 = "Neto Gravado IVA 0%"
COL_TOTAL_NETO = "Total Neto Gravado"


def monto(valor: float) -> str:
    """Formato de importes del CSV: coma decimal (1234,56)."""
    return f"{valor:.2f}".replace(".", ",")


def leer_encabezado(ruta) -> list[str]:
    """Solo se usa el encabezado de la plantilla oficial (nombres y orden de columnas)."""
    with open(ruta, encoding="iso-8859-1", newline="") as f:
        return next(csv.reader(f, delimiter=";"))


def generar_csv(encabezado: list[str], delimitador: str, filas: list[dict]) -> bytes:
    """CSV a partir del encabezado oficial y una lista de {columna: valor}. Las columnas no informadas
    (importes que no aplican) van en 0,00."""
    faltantes = {c for fila in filas for c in fila} - set(encabezado)
    if faltantes:
        raise ValueError(f"La plantilla no tiene las columnas {sorted(faltantes)}")
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=delimitador, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writerow(encabezado)
    for fila in filas:
        w.writerow([fila.get(col, "0,00") for col in encabezado])
    return buf.getvalue().encode("iso-8859-1", errors="replace")


def multipart(boundary: str, campos: dict, nombre_archivo: str, contenido: bytes,
              tipo: str = "application/vnd.ms-excel") -> bytes:  # fmt: skip
    """multipart/form-data con el mismo orden que la UI: campos de texto y el archivo al final."""
    body = b""
    for k, v in campos.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{nombre_archivo}"\r\n'
             f"Content-Type: {tipo}\r\n\r\n").encode()  # fmt: skip
    return body + contenido + f"\r\n--{boundary}--\r\n".encode()


class Importacion:
    """Estado del escenario por usuario virtual: origen (se busca una vez), plantilla y numeración."""

    def __init__(self, user: UsuarioApi):
        cfg = user.settings.importacion
        if cfg is None:
            raise FallaDatos(
                f"{user.ctx.etiqueta} falta la sección 'importacion:' del ambiente (origen_codigo, "
                "tipo_comprobante, moneda, tipo_cambio, importe_min, importe_max)"
            )
        if user.settings.plataforma is None:
            raise FallaDatos(f"{user.ctx.etiqueta} la importación necesita 'plataforma.front_url' (stream del job)")
        self.user, self.cfg = user, cfg
        self.encabezado = leer_encabezado(user.settings.ruta(cfg.plantilla))
        # Punto de venta propio y numeración correlativa por ciclo: sin comprobantes duplicados entre ciclos.
        self.pto_venta = random.randint(1, 9999)
        self.proximo_numero = random.randint(1, 90_000_000)
        self.origen: dict | None = None

    def ejecutar(self):
        return ejecutar_ciclo(self.user, PREFIJO, N_FLUJO, self._ciclo)

    # ───────────── ciclo ─────────────

    def _ciclo(self, r: dict) -> None:
        u, m = self.user, self.user.ctx.maestros
        self._paso01_origen()
        self._paso02_empresa_libre()
        antes = con_sesion(u, grilla_compras, u, api.N_ANTES, m.emp_codigo, m.periodo_fiscal_cod)[1]
        r["comprobantes_antes"] = antes

        contenido, nombre = self._generar_archivo(r)
        temp_id = self._paso04_subir(contenido, nombre)
        self._paso05_validacion_preliminar(temp_id, nombre, len(contenido))
        id_archivo = self._paso06_incorporar(temp_id, nombre, r)
        self._paso07_procesamiento(id_archivo, r)
        resumen = self._paso08_resumen(id_archivo, r)
        ids = self._paso09_lineas(id_archivo, resumen, r)
        self._paso10_iniciar(ids)
        self._paso11_validar_definitivos(ids, r)
        self._paso12_cuota(ids)
        job_id, aceptados = self._paso13_lanzar(ids, r)
        self._paso14_seguimiento_job(job_id, r)

        despues = con_sesion(u, grilla_compras, u, api.N_DESPUES, m.emp_codigo, m.periodo_fiscal_cod)[1]
        nuevos = despues - antes
        r["comprobantes_nuevos"] = nuevos
        if nuevos < aceptados:
            error_aparte(u, api.N_DESPUES, f"Se esperaban {aceptados} comprobantes nuevos y hay {nuevos} "
                                           f"(antes={antes}, despues={despues}) empresa={m.emp_codigo}")  # fmt: skip
            raise FallaTrabajo(f"{u.ctx.etiqueta} se crearon {nuevos} de {aceptados} comprobantes")
        logger.info("%s IMPO OK: %d comprobantes nuevos (filas CSV=%d)", u.ctx.etiqueta, nuevos, self.cfg.lote_n)

    # ───────────── pasos ─────────────

    def _falla(self, mensaje: str) -> FallaTrabajo:
        return FallaTrabajo(f"{self.user.ctx.etiqueta} {mensaje}")

    def _paso01_origen(self) -> None:
        """Origen por CÓDIGO (no por id): id, nombre de archivo y delimitador. Se busca una vez por usuario."""
        if self.origen:
            return
        u, emp = self.user, self.user.ctx.maestros.emp_codigo
        j = con_sesion(u, api.origenes, u, emp, COMPRA_VENTA, COMPROBANTE_CERTIFICADO)
        lista = (j.get("data") or {}).get("data") or []
        codigo = self.cfg.origen_codigo
        o = next((x for x in lista if str(x.get("CodigoOrigen")).upper() == codigo.upper()), None)
        if o is None:
            disponibles = ", ".join(f"{x.get('CodigoOrigen')}={x.get('Descripcion')}" for x in lista)
            raise self._falla(f"{api.N_ORIGEN}: no existe el origen {codigo!r} en la empresa {emp}. "
                              f"Disponibles: {disponibles}")  # fmt: skip
        self.origen = {
            "id": int(o["IdOrigen"]),
            "descripcion": o.get("Descripcion"),
            "nombre": o.get("NombreArchivo") or "",
            "extension": o.get("Extension") or "csv",
            "delimitador": o.get("CaracterDelimitador") or ";",
        }
        logger.info("%s origen %s → id=%s (%s)", u.ctx.etiqueta, codigo, self.origen["id"], self.origen["descripcion"])

    def _paso02_empresa_libre(self) -> None:
        """El backend permite una importación a la vez por empresa: esperar a que esté libre."""
        u, m = self.user, self.user.ctx.maestros
        limite = time.time() + self.cfg.espera_empresa_libre_s
        while True:
            d = con_sesion(u, api.estado_compras, u, m.emp_codigo, m.periodo_fiscal_id).get("data") or {}
            if not d.get("enCurso"):
                return
            if time.time() > limite:
                raise self._falla(
                    f"{api.N_EMPRESA_LIBRE}: la empresa {m.emp_codigo} sigue con otra importación en curso después "
                    f"de {self.cfg.espera_empresa_libre_s:.0f}s (estado={d.get('estado')}, "
                    f"periodo={d.get('periodoEnCurso')})"
                )
            gevent.sleep(self.cfg.intervalo_sondeo_s)

    def _generar_archivo(self, r: dict) -> tuple[bytes, str]:
        cfg, m = self.cfg, self.user.ctx.maestros
        cod = str(m.periodo_fiscal_cod)
        abrev = (m.proveedor_tipo_doc_abrev or "").upper()
        tipo_doc = TIPO_DOC_AFIP.get(abrev)
        if not tipo_doc:
            raise self._falla(f"tipo de documento del proveedor desconocido: {abrev!r} (proveedor id={m.proveedor_id})")
        filas = []
        for i in range(cfg.lote_n):
            importe = round(random.uniform(cfg.importe_min, cfg.importe_max), 2)
            filas.append({
                COL_FECHA: f"{cod[:4]}-{cod[4:6]}-{(i % 28) + 1:02d}",
                COL_TIPO_COMP: cfg.tipo_comprobante,
                COL_PTO_VENTA: str(self.pto_venta),
                COL_NUMERO: str(self.proximo_numero + i),
                COL_TIPO_DOC: tipo_doc,
                COL_NRO_DOC: str(m.proveedor_nro_doc),
                COL_DENOMINACION: m.proveedor_rz or "",
                COL_TOTAL: monto(importe),
                COL_MONEDA: cfg.moneda,
                COL_TIPO_CAMBIO: monto(cfg.tipo_cambio),
                # Todo el importe como Neto Gravado IVA 0% (sin remanente "no gravado": el backend
                # exigiría un tipo de movimiento por defecto configurado).
                COL_NETO_IVA_0: monto(importe),
                COL_TOTAL_NETO: monto(importe),
            })  # fmt: skip
        self.proximo_numero += cfg.lote_n
        contenido = generar_csv(self.encabezado, self.origen["delimitador"], filas)
        base = self.origen["nombre"].replace("<PERIODO>", cod) or f"importacion_{cod}"
        nombre = f"{base}.{self.origen['extension']}"
        r.update({"archivo": nombre, "filas": cfg.lote_n})
        return contenido, nombre

    def _paso04_subir(self, contenido: bytes, nombre: str) -> str:
        u, m = self.user, self.user.ctx.maestros
        boundary = "----GdcImp" + uuid.uuid4().hex
        campos = {"idOrigen": self.origen["id"], "empCodigo": m.emp_codigo, "periodoId": m.periodo_fiscal_id,
                  "fileName": nombre, "fileSize": len(contenido),
                  "compraVenta": COMPRA_VENTA, "comprobanteCertificado": COMPROBANTE_CERTIFICADO}  # fmt: skip
        j = con_sesion(u, api.select_file, u, multipart(boundary, campos, nombre, contenido), boundary)
        temp_id = (j.get("fileInfo") or {}).get("fileTempId")
        if not temp_id:
            raise self._falla(f"{api.N_SUBIR}: el servidor no devolvió fileTempId: {json.dumps(j)[:300]}")
        return temp_id

    def _paso05_validacion_preliminar(self, temp_id: str, nombre: str, tam: int) -> None:
        u, m = self.user, self.user.ctx.maestros
        # Este servicio recibe el período como CÓDIGO (AAAAMM), no como id.
        j = con_sesion(u, api.validate_preliminary, u, {
            "empCodigo": m.emp_codigo, "periodoId": int(m.periodo_fiscal_cod), "idOrigen": self.origen["id"],
            "fileTempId": temp_id, "fileName": nombre, "fileSize": tam,
        })  # fmt: skip
        invalidas = [k for k, v in (j.get("validation") or {}).items() if v is False]
        if invalidas:
            raise self._falla(f"{api.N_VALIDACION}: validaciones no superadas: {invalidas}")

    def _paso06_incorporar(self, temp_id: str, nombre: str, r: dict) -> int:
        u, m = self.user, self.user.ctx.maestros
        j = con_sesion(u, api.incorporar, u, {
            "empCodigo": m.emp_codigo, "periodoId": m.periodo_fiscal_id, "idOrigen": self.origen["id"],
            "fileTempId": temp_id, "fileNameOriginal": nombre,
        })  # fmt: skip
        id_archivo = (j.get("data") or {}).get("idArchivo")
        if not isinstance(id_archivo, int):
            raise self._falla(f"{api.N_INCORPORAR}: el servidor no devolvió idArchivo: {json.dumps(j)[:300]}")
        r["id_archivo"] = id_archivo
        return id_archivo

    def _paso07_procesamiento(self, id_archivo: int, r: dict) -> None:
        u, m = self.user, self.user.ctx.maestros
        limite = time.time() + self.cfg.timeout_proceso_archivo_s
        while True:
            d = con_sesion(u, api.estado_archivo, u, id_archivo, m.emp_codigo)
            if d.get("mensajeError"):
                raise self._falla(f"{api.N_PROCESAMIENTO}: {d.get('estadoArchivo')}: {d.get('mensajeError')}")
            if d.get("finalizado"):
                r["estado_archivo"] = d.get("estadoArchivo")
                return
            if time.time() > limite:
                raise self._falla(
                    f"{api.N_PROCESAMIENTO}: el archivo {id_archivo} no terminó de procesarse en "
                    f"{self.cfg.timeout_proceso_archivo_s:.0f}s ({d.get('lineasProcesadas')}/{d.get('totalLineas')} "
                    f"líneas, {d.get('porcentajeAvance')}%)"
                )
            gevent.sleep(self.cfg.intervalo_sondeo_s)

    def _paso08_resumen(self, id_archivo: int, r: dict) -> dict:
        u = self.user
        s = con_sesion(u, api.resumen_archivo, u, id_archivo, u.ctx.maestros.emp_codigo).get("summary") or {}
        claves = ("totalRegistros", "totalOk", "totalWarning", "totalError", "totalSeleccionables")
        r["lineas"] = {k: s.get(k) for k in claves}
        return s  # las líneas con error se informan en el paso 09, con el motivo de cada una

    def _paso09_lineas(self, id_archivo: int, resumen: dict, r: dict) -> list:
        """Líneas de ESTE archivo (filtro idArchivo), paginadas. Nunca se toman líneas de otros archivos.
        Devuelve los ids importables e informa las rechazadas agrupadas por motivo."""
        u, m, tam = self.user, self.user.ctx.maestros, self.cfg.tam_pagina
        ids, errores, pagina = [], {}, 1
        while True:
            j = con_sesion(u, api.lineas_archivo, u, {
                "empCodigo": m.emp_codigo, "page": pagina, "limit": tam, "search": "",
                "filter": {"periodo": m.periodo_fiscal_id, "compraVenta": COMPRA_VENTA,
                           "comprobanteCertificado": COMPROBANTE_CERTIFICADO, "idArchivo": id_archivo},
            })  # fmt: skip
            lineas = j.get("data") or []
            for ln in lineas:
                if ln.get("idArchivo") != id_archivo:
                    continue
                if ln.get("estado") in ("O", "W"):  # O = ok, W = advertencia: importables
                    ids.append(ln["idLineaArchivo"])
                else:
                    motivo = ln.get("mensajeError") or f"estado {ln.get('estado')} sin mensaje"
                    errores[motivo] = errores.get(motivo, 0) + 1
            if len(lineas) < tam or pagina * tam >= (j.get("total") or 0):
                break
            pagina += 1
        if errores:
            detalle = "; ".join(f"{mo} (x{n})" for mo, n in sorted(errores.items(), key=lambda x: -x[1]))
            r["lineas_rechazadas"] = detalle
            error_aparte(u, "IMPO 09 Lineas rechazadas por el backend",
                         f"{sum(errores.values())} de {resumen.get('totalRegistros')} líneas del archivo "
                         f"{id_archivo}: {detalle}")  # fmt: skip
        if len(ids) != resumen.get("totalSeleccionables"):
            logger.warning("%s líneas importables encontradas=%d vs resumen=%s", u.ctx.etiqueta, len(ids),
                           resumen.get("totalSeleccionables"))  # fmt: skip
        if not ids:
            motivo = f": {next(iter(errores))}" if errores else ""
            raise self._falla(f"{api.N_LINEAS}: ninguna línea del archivo {id_archivo} se puede importar{motivo}")
        return ids

    def _cuerpo_definitivo(self, ids: list) -> dict:
        m = self.user.ctx.maestros
        return {"empCodigo": m.emp_codigo, "periodoFiscalId": m.periodo_fiscal_id, "idOrigen": self.origen["id"],
                "compraVenta": COMPRA_VENTA, "idsLineaArchivo": ids, "replaceExisting": False}  # fmt: skip

    def _paso10_iniciar(self, ids: list) -> None:
        u, m = self.user, self.user.ctx.maestros
        j = con_sesion(u, api.iniciar, u, {
            "empCodigo": m.emp_codigo, "periodoFiscalId": m.periodo_fiscal_id, "idsLineaArchivo": ids,
            "compraVenta": COMPRA_VENTA, "comprobanteCertificado": COMPROBANTE_CERTIFICADO,
            "idOrigen": self.origen["id"],
        })  # fmt: skip
        # Si el período ya tiene comprobantes la UI pregunta si reemplazarlos; el escenario siempre AGREGA
        # (replaceExisting=False), igual que la opción por defecto.
        existentes = ((j.get("data") or {}).get("existingVouchersInfo") or {}).get("compraCount")
        if existentes:
            logger.info("%s el período ya tiene %s comprobantes de compra: se agregan", u.ctx.etiqueta, existentes)

    def _paso11_validar_definitivos(self, ids: list, r: dict) -> None:
        u = self.user
        j = con_sesion(u, api.validar_definitivos, u, self._cuerpo_definitivo(ids))
        c = (((j.get("data") or {}).get("resultado") or {}).get("compras")) or {}
        r["validacion"] = {k: c.get(k) for k in ("totalProcesados", "totalValidos", "totalRechazados")}
        if c.get("totalRechazados"):
            error_aparte(u, "IMPO 11 Comprobantes rechazados",
                         f"{c.get('totalRechazados')} de {c.get('totalProcesados')} rechazados: {c.get('rechazos')}")
        if not c.get("totalValidos"):
            raise self._falla(f"{api.N_VALIDAR_DEF}: ningún comprobante pasó la validación definitiva ({c})")

    def _paso12_cuota(self, ids: list) -> None:
        u = self.user
        d = con_sesion(u, api.cuota, u, self._cuerpo_definitivo(ids)).get("data") or {}
        if not d.get("quotaOk") or d.get("excedeCuota"):
            raise self._falla(f"{api.N_CUOTA}: cuota excedida: registrados={d.get('cantidadRegistrada')} "
                              f"a importar={d.get('cantidadAImportar')} "
                              f"cuota={d.get('cuotaComprobantes')}")  # fmt: skip

    def _paso13_lanzar(self, ids: list, r: dict) -> tuple[str, int]:
        u = self.user
        j = con_sesion(u, api.lanzar, u, self._cuerpo_definitivo(ids))
        job = ((j.get("data") or {}).get("data")) or {}
        if not job.get("jobId"):
            raise self._falla(f"{api.N_LANZAR}: el servidor no devolvió jobId: {json.dumps(j)[:300]}")
        r.update({"job_id": job["jobId"], "aceptados": job.get("acceptedVouchers")})
        return job["jobId"], int(job.get("acceptedVouchers") or 0)

    def _paso14_seguimiento_job(self, job_id: str, r: dict) -> None:
        u, timeout = self.user, self.cfg.timeout_job_s
        ultimo = api.seguir_job(u, job_id, timeout, self.cfg.intervalo_sondeo_s) or {}
        prog = ultimo.get("progress") or {}
        r["job"] = {"estado": ultimo.get("status"), "procesados": prog.get("processedVouchers"),
                    "total": prog.get("totalVouchers"), "fallidos": prog.get("failedVouchers"),
                    "advertencias": ultimo.get("warnings") or [], "errores": ultimo.get("errors") or []}  # fmt: skip
        if not ultimo.get("finishedAt"):
            error_aparte(u, "IMPO 14 Job no termino",
                         f"job {job_id} sin terminar después de {timeout:.0f}s "
                         f"(estado={ultimo.get('status')}, avance={prog.get('percentComplete')}%)")  # fmt: skip
            raise self._falla(f"{api.N_JOB}: el job {job_id} no terminó en {timeout:.0f}s")
        if (not str(ultimo.get("status", "")).startswith("COMPLETED") or ultimo.get("errors")
                or prog.get("failedVouchers")):  # fmt: skip
            error_aparte(u, "IMPO 14 Job con errores",
                         f"job {job_id} estado={ultimo.get('status')} fallidos={prog.get('failedVouchers')} "
                         f"errores={(ultimo.get('errors') or [])[:3]}")  # fmt: skip
            raise self._falla(f"{api.N_JOB}: el job {job_id} terminó con estado {ultimo.get('status')}")
