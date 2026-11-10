"""Modificación masiva de cabecera de comprobantes de compra (antes tasks/gdc_modificacion_masiva.py).

Automatiza la grabación har_input/gdccomprobantesmodificar-JMeter.json: en la grilla Comprobantes > Compras
se seleccionan comprobantes del período, se abre "Modificación masiva" y se cambian la Condición fiscal y la
Provincia. Después se verifica en la grilla que quedaron con los valores nuevos.

Pasos (nombre en Locust):
    MODIF 01 Comprobantes del periodo   grilla de compras del período (ids y valores actuales)
    MODIF 02 Periodo protegido          el período fiscal no debe estar protegido
    MODIF 03 Seleccion protegida        ningún comprobante seleccionado en un período protegido
    MODIF 04 Condiciones IVA            catálogo del diálogo (valida los códigos configurados)
    MODIF 05 Provincias                 catálogo del diálogo (valida los códigos configurados)
    MODIF 06 Modificar cabecera         modificacion-masiva/cabecera (sincrónico)
    MODIF 07 Verificacion               relee la página y compara por id
    MODIF 00 Modificacion completa      el ciclo entero (FLUJO)

⚠ Modifica datos: cambia la cabecera de comprobantes reales del período. Solo QA o ambientes de prueba.
"""

from __future__ import annotations

import logging
import math
import random

from holistor_stress.api import rutas
from holistor_stress.api.comprobantes import gdc, grilla_compras, periodo_guion
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.errores import FallaTrabajo
from holistor_stress.flows.ciclo import ejecutar_ciclo, error_aparte
from holistor_stress.flows.sesion import con_sesion

logger = logging.getLogger("holistor_stress")

PREFIJO = "MODIF"
N_FLUJO = "MODIF 00 Modificacion completa (punta a punta)"
N_COMPROBANTES = "MODIF 01 Comprobantes del periodo"
N_PERIODO_PROTEGIDO = "MODIF 02 Periodo protegido"
N_SELECCION_PROTEGIDA = "MODIF 03 Seleccion protegida"
N_COND_IVA = "MODIF 04 Condiciones IVA"
N_PROVINCIAS = "MODIF 05 Provincias"
N_MODIFICAR = "MODIF 06 Modificar cabecera"
N_VERIFICACION = "MODIF 07 Verificacion"


class ModificacionMasiva:
    def __init__(self, user: UsuarioApi):
        self.user, self.cfg = user, user.settings.modificacion

    def ejecutar(self):
        return ejecutar_ciclo(self.user, PREFIJO, N_FLUJO, self._ciclo, seleccion=self.cfg.seleccion)

    def _falla(self, mensaje: str) -> FallaTrabajo:
        return FallaTrabajo(f"{self.user.ctx.etiqueta} {mensaje}")

    def _ciclo(self, r: dict) -> None:
        pagina, limite, filas, total = self._paso01_comprobantes(r)
        seleccion = self._seleccion(filas, r)
        self._paso02_periodo_protegido()
        self._paso03_seleccion_protegida(seleccion)
        cond = self._nuevo_valor(N_COND_IVA, "condiciones-iva", "abreviatura", self.cfg.cond_fiscal,
                                 filas[0].get("condFiscal"))  # fmt: skip
        prov = self._nuevo_valor(N_PROVINCIAS, "provincias", "nombre", self.cfg.provincia, filas[0].get("provin"))
        r.update({"cond_fiscal": f"{filas[0].get('condFiscal')} -> {cond}",
                  "provincia": f"{filas[0].get('provin')} -> {prov}"})  # fmt: skip
        self._paso06_modificar(seleccion, cond, prov, r)
        self._paso07_verificar(pagina, limite, filas, total, cond, prov, r)

    def _grilla(self, nombre: str, pagina: int, limite: int):
        u, m = self.user, self.user.ctx.maestros
        return con_sesion(u, grilla_compras, u, nombre, m.emp_codigo, m.periodo_fiscal_cod, pagina, limite)

    def _paso01_comprobantes(self, r: dict):
        """Lote: una página al azar (los usuarios no tocan siempre los mismos comprobantes).
        Todos: la primera página, solo para tener valores actuales y una muestra a verificar."""
        lote = self.cfg.seleccion == "lote"
        limite = self.cfg.lote_n if lote else 100
        filas, total = self._grilla(N_COMPROBANTES, 1, limite)
        pagina = 1
        paginas = math.ceil(total / limite) if total else 0
        if lote and paginas > 1:
            pagina = random.randint(1, paginas)
            if pagina != 1:
                filas, total = self._grilla(N_COMPROBANTES, pagina, limite)
        if not filas:
            m = self.user.ctx.maestros
            raise self._falla(f"{N_COMPROBANTES}: la empresa {m.emp_codigo} no tiene comprobantes de compra en "
                              f"{periodo_guion(m.periodo_fiscal_cod)} (total={total})")  # fmt: skip
        r["comprobantes_periodo"] = total
        return pagina, limite, filas, total

    def _seleccion(self, filas: list, r: dict) -> dict:
        """Cuerpo común de la selección (mismo formato que la grilla de la UI)."""
        m = self.user.ctx.maestros
        periodo = periodo_guion(m.periodo_fiscal_cod)
        base = {"empCodigo": m.emp_codigo, "periodoFiscalCodDesde": periodo, "periodoFiscalCodHasta": periodo}
        if self.cfg.seleccion == "todos":
            r["seleccionados"] = "todos"
            return {**base, "ccpraIds": [], "isExclude": True}
        ids = [f["cCpraId"] for f in filas]
        r["seleccionados"] = len(ids)
        return {**base, "ccpraIds": ids, "isExclude": False}

    def _paso02_periodo_protegido(self) -> None:
        u, m = self.user, self.user.ctx.maestros
        j = con_sesion(u, gdc, u, "GET", rutas.PERIODO_PROTEGIDO, N_PERIODO_PROTEGIDO,
                       params={"empCodigo": m.emp_codigo, "periodoFiscalId": m.periodo_fiscal_id})  # fmt: skip
        if (j.get("data") or {}).get("protegido"):
            raise self._falla(f"{N_PERIODO_PROTEGIDO}: el período {periodo_guion(m.periodo_fiscal_cod)} de la "
                              f"empresa {m.emp_codigo} está protegido")  # fmt: skip

    def _paso03_seleccion_protegida(self, seleccion: dict) -> None:
        u = self.user
        d = con_sesion(u, gdc, u, "POST", rutas.MODIF_SELECCION_PROTEGIDA, N_SELECCION_PROTEGIDA,
                       json=seleccion).get("data") or {}  # fmt: skip
        if d.get("protegido"):
            raise self._falla(f"{N_SELECCION_PROTEGIDA}: la selección incluye comprobantes de un período "
                              f"protegido: {d.get('mensaje')}")  # fmt: skip

    def _nuevo_valor(self, nombre: str, catalogo: str, campo_desc: str, candidatos: list[int], actual):
        """Primer código configurado distinto del actual, validado contra el catálogo."""
        u = self.user
        j = con_sesion(u, gdc, u, "GET", f"{rutas.MODIF_CATALOGO}/{catalogo}", nombre)
        validos = {x.get("codigo"): x.get(campo_desc) for x in (j.get("data") or [])}
        invalidos = [c for c in candidatos if c not in validos]
        if invalidos:
            disponibles = ", ".join(f"{k}={v}" for k, v in validos.items())
            raise self._falla(f"{nombre}: los códigos {invalidos} no existen. Disponibles: {disponibles}")
        return next((c for c in candidatos if c != actual), candidatos[0])

    def _paso06_modificar(self, seleccion: dict, cond: int, prov: int, r: dict) -> None:
        u = self.user
        j = con_sesion(u, gdc, u, "POST", rutas.MODIF_CABECERA, N_MODIFICAR,
                       json={**seleccion, "CCpraCondFiscal": cond, "CCpraProvin": prov})  # fmt: skip
        d = j.get("data") or {}
        r["respuesta"] = d.get("mensaje")
        if d.get("advertencia"):
            r["advertencia"] = d["advertencia"]
            logger.warning("%s advertencia del servidor: %s", u.ctx.etiqueta, d["advertencia"])

    def _paso07_verificar(self, pagina: int, limite: int, filas: list, total: int, cond: int, prov: int,
                          r: dict) -> None:  # fmt: skip
        """Relee la misma página y compara por id: todos deben tener los valores nuevos.

        Se relee con el MISMO tamaño de página del paso 01. (El original usaba len(filas): si la página al azar
        era la última e incompleta, la relectura caía en otra ventana de comprobantes y el ciclo fallaba.)
        """
        u = self.user
        despues, total_despues = self._grilla(N_VERIFICACION, pagina, limite)
        por_id = {f["cCpraId"]: f for f in despues}
        mal = [(i, por_id[i].get("condFiscal"), por_id[i].get("provin"))
               for i in (f["cCpraId"] for f in filas) if i in por_id
               and (por_id[i].get("condFiscal") != cond or por_id[i].get("provin") != prov)]  # fmt: skip
        verificados = sum(1 for f in filas if f["cCpraId"] in por_id)
        r["verificados"] = f"{verificados - len(mal)}/{verificados} con los valores nuevos"
        if verificados < len(filas):
            logger.warning("%s %d comprobantes no aparecen en la página %d al releer", u.ctx.etiqueta,
                           len(filas) - verificados, pagina)  # fmt: skip
        if total_despues != total:
            error_aparte(u, "MODIF 07 Cantidad de comprobantes",
                         f"el período tenía {total} comprobantes y después de modificar tiene {total_despues}")
        if mal:
            error_aparte(u, "MODIF 07 Comprobantes sin modificar",
                         f"{len(mal)} de {verificados} no quedaron con condFiscal={cond} provin={prov}; "
                         f"ejemplos (id, condFiscal, provin): {mal[:5]}")  # fmt: skip
            raise self._falla(f"{N_VERIFICACION}: {len(mal)} de {verificados} comprobantes no quedaron modificados")
        if not verificados:
            raise self._falla(f"{N_VERIFICACION}: ningún comprobante seleccionado aparece al releer la página {pagina}")
