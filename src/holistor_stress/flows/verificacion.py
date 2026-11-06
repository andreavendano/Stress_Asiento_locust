"""Verificaciones de un trabajo terminado (paso 01.7). Las reglas son puras y devuelven errores."""

from __future__ import annotations

import re
from typing import Any

from holistor_stress.api import control as api_control
from holistor_stress.api.http import UsuarioApi
from holistor_stress.core.context import Envio, id_asiento
from holistor_stress.flows.sesion import con_sesion

PISTA_ARCHIVO = " → revisar EmpMod, nuc_EjerEco y nuc_TipoAsiento"
_FECHA = re.compile(r"(\d{2})/(\d{2})/(\d{4})|(\d{4})-(\d{2})-(\d{2})")

# ─────────────── reglas puras ───────────────


def asientos_ok(devueltos: list[dict]) -> int:
    return sum(1 for a in devueltos if str(a.get("status", "")).upper() == "OK")


def verificar_destino(enviados: list[dict], devueltos: list[dict], empresa: int, ejercicio: int) -> list[str]:
    """Uno por enviado, todos OK, en su empresa y ejercicio, y con los mismos IDs que se enviaron."""
    errores = []
    if len(devueltos) != len(enviados):
        errores.append(f"se enviaron {len(enviados)} asientos y el resultado trae {len(devueltos)}")
    no_ok = [a for a in devueltos if str(a.get("status", "")).upper() != "OK"]
    if no_ok:
        primero = no_ok[0]
        detalle = str(primero.get("errores") or primero.get("status"))[:200]
        pista = PISTA_ARCHIVO if "Error al crear archivo" in detalle else ""
        errores.append(f"{len(no_ok)} de {len(devueltos)} asientos no OK: {detalle}{pista}")
    otro_destino = [a for a in devueltos if _int(a.get("empresa")) != empresa or _int(a.get("ejercicio")) != ejercicio]
    if otro_destino:
        a = otro_destino[0]
        errores.append(
            f"{len(otro_destino)} asientos fuera de su destino (empresa {a.get('empresa')}, "
            f"ejercicio {a.get('ejercicio')}; se esperaba {empresa}/{ejercicio})"
        )
    ids_env = sorted(id_asiento(a).lower() for a in enviados)
    ids_dev = sorted(id_asiento(a).lower() for a in devueltos)
    if ids_env != ids_dev:
        errores.append("los IDs devueltos no son los enviados")
    return errores


def fechas_de_lineas(data: Any) -> list[str]:
    """Fechas AAAA-MM-DD que aparecen en las líneas de resultado-proceso (dd/mm/aaaa o ISO)."""
    fechas = []
    for linea in (data or {}).get("lineas") or []:
        if isinstance(linea, dict):
            campos = ("etiqueta", "texto", "descripcion", "linea", "fecha", "leyenda")
            texto = " ".join(str(linea[c]) for c in campos if linea.get(c))
        else:
            texto = str(linea)
        if m := _FECHA.search(texto):
            fechas.append(f"{m[3]}-{m[2]}-{m[1]}" if m[3] else f"{m[4]}-{m[5]}-{m[6]}")
    return fechas


def verificar_fechas(fechas: list[str], desde: str, hasta: str) -> list[str]:
    if not fechas:
        return ["no se pudieron leer las fechas de los asientos (resultado-proceso)"]
    desde, hasta = desde[:10], hasta[:10]
    fuera = [f for f in fechas if not desde <= f <= hasta]
    return [f"{len(fuera)} asientos con fecha fuera de {desde} a {hasta} (ej. {fuera[0]})"] if fuera else []


def verificar_control(data: Any, enviados: int) -> list[str]:
    """jobs/estado: todos aceptados, ninguno pendiente ni rechazado."""
    d = data or {}
    resumen = f"aceptados {d.get('aceptados')}, pendientes {d.get('pendientes')}, rechazados {d.get('rechazados')}"
    if _int(d.get("rechazados")) or _int(d.get("pendientes")) or _int(d.get("aceptados")) != enviados:
        return [f"tabla de control: {resumen} de {enviados} enviados"]
    return []


def _int(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


# ─────────────── pasos ───────────────


def verificar_fechas_asientos(user: UsuarioApi, envio: Envio) -> list[str]:
    data = con_sesion(user, api_control.resultado_proceso, user, envio.claves())
    periodo = user.ctx.periodo
    return verificar_fechas(fechas_de_lineas(data), periodo.fecha_desde, periodo.fecha_hasta)


def consultar_control(user: UsuarioApi, envio: Envio) -> tuple[dict, list[str]]:
    data = con_sesion(user, api_control.jobs_estado, user, envio.claves()) or {}
    control = {k: data.get(k) for k in ("estado", "total", "aceptados", "pendientes", "rechazados")}
    return control, verificar_control(data, len(envio.asientos))
