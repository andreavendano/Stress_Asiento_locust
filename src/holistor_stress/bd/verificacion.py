"""Ejecuta la verificación de una corrida en la base y guarda verificacion_resultado.json.

    holistor-stress-verificar --probar                    # prueba la conexión y los permisos
    holistor-stress-verificar reports/<carpeta>           # verifica una corrida (y regenera su informe)

Al terminar cada corrida con trabajos se ejecuta sola si `bd.verificar_al_terminar` está activo.
⚠ Verificar apenas termina la corrida: una corrida posterior con reemplazar recrea los asientos.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from holistor_stress.bd.conexion import BDError, ConexionBD, ConfigBD
from holistor_stress.config import ConfigError, cargar_settings
from holistor_stress.reporting.resumen import construir_resumen
from holistor_stress.reporting.sql_verificacion import consultas

ARCHIVO = "verificacion_resultado.json"


def _valor(v):
    if isinstance(v, datetime | date):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v if v is None or isinstance(v, int | float | str | bool) else str(v)


def abrir_conexiones(cfg: ConfigBD, bases_por_tenant: Mapping[int, str], pila: ExitStack):
    """(conexión a la base del .env, tenantId → conexión a la base de ese tenant). Todas de solo consulta."""
    principal = pila.enter_context(ConexionBD(cfg))
    abiertas = {cfg.base.lower(): principal}
    por_tenant = {}
    for tenant, base in bases_por_tenant.items():
        if base.lower() not in abiertas:
            abiertas[base.lower()] = pila.enter_context(ConexionBD(replace(cfg, base=base)))
        por_tenant[str(tenant)] = abiertas[base.lower()]
    return principal, por_tenant


def verificar_corrida(carpeta: Path, conexion: ConexionBD, por_tenant: Mapping[str, ConexionBD] | None = None) -> dict:
    """Ejecuta las consultas de la corrida y escribe verificacion_resultado.json.

    Cada consulta va a la base del tenant de su trabajo (por_tenant); si el tenant no está, a `conexion`.
    """
    por_tenant = por_tenant or {}
    resumen = construir_resumen(carpeta)
    lista = consultas(resumen)
    usadas = {c.tenant: por_tenant.get(c.tenant, conexion).cfg.base for c in lista}
    resultado: dict = {
        "ejecutada": datetime.now().isoformat(timespec="seconds"),
        "base": ", ".join(sorted(set(usadas.values()))) or conexion.cfg.base,
        "bases": {t: b for t, b in sorted(usadas.items()) if t},
        "trabajos": {},
        "huerfanos": {},
        "errores": [],
    }
    for c in lista:
        try:
            columnas, filas = por_tenant.get(c.tenant, conexion).consultar(c.sql)
        except BDError as e:
            resultado["errores"].append(f"{c.titulo}: {e}")
            continue
        registros = [{k: _valor(v) for k, v in zip(columnas, fila, strict=True)} for fila in filas]
        if c.tipo == "trabajo" and registros:
            r = registros[0]
            resultado["trabajos"][c.clave] = {
                "asientos_ok_control": r.get("asientos_ok_control"),
                "comprobantes_contabilizados": r.get("comprobantes_contabilizados"),
            }
        elif c.tipo == "huerfanos":
            resultado["huerfanos"].setdefault(c.clave, {})["asientos"] = registros
        elif c.tipo == "huerfanos_comprobantes" and registros:
            resultado["huerfanos"].setdefault(c.clave, {})["comprobantes_contabilizados"] = registros[0].get(
                "comprobantes_contabilizados"
            )
    (carpeta / ARCHIVO).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return resultado


def probar(conexion: ConexionBD) -> list[str]:
    """Datos de la conexión y advertencias de permisos (para --probar)."""
    _, version = conexion.consultar(
        "SELECT CAST(SERVERPROPERTY('ProductVersion') AS varchar(30)), CAST(SERVERPROPERTY('Edition') AS varchar(60)), "
        "DB_NAME(), SUSER_SNAME()"
    )
    _, permisos = conexion.consultar(
        "SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT'), "
        "HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'UPDATE'), "
        "HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'DELETE')"
    )
    _, tablas = conexion.consultar(
        "SELECT name FROM sys.tables WHERE name IN ('nuc_AsientosOtrosModulos', 'gdc_ComprobanteCompraCab', "
        "'gdc_ComprobanteVentaCab')"
    )
    v = version[0]
    lineas = [f"Conectado: {v[2]} como {v[3]} · SQL Server {v[0]} ({v[1]})"]
    encontradas = {t[0] for t in tablas}
    faltan = {"nuc_AsientosOtrosModulos", "gdc_ComprobanteCompraCab", "gdc_ComprobanteVentaCab"} - encontradas
    lineas.append("Tablas de verificación: " + ("OK" if not faltan else f"faltan {', '.join(sorted(faltan))}"))
    if any(permisos[0]):
        lineas.append(
            "ADVERTENCIA: el usuario tiene permisos de escritura. El framework solo ejecuta SELECT, pero conviene "
            "un usuario de solo lectura (db_datareader)."
        )
    return lineas


def main(argv: list[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="holistor-stress-verificar", description=__doc__.splitlines()[0])
    p.add_argument("carpetas", nargs="*", help="Carpetas de corridas a verificar")
    p.add_argument("--target-env", default="qa")
    p.add_argument("--probar", action="store_true", help="Solo prueba la conexión y los permisos")
    a = p.parse_args(argv)
    if not a.probar and not a.carpetas:
        p.error("indicar --probar o al menos una carpeta de corrida")

    try:
        settings = cargar_settings(a.target_env)
        with ExitStack() as pila:
            conexion, por_tenant = abrir_conexiones(ConfigBD.desde(settings), settings.bd.bases_por_tenant, pila)
            if a.probar:
                print("\n".join(probar(conexion)))
                return 0
            from holistor_stress.reporting import informe

            for carpeta in map(Path, a.carpetas):
                if not informe.es_corrida(carpeta):
                    print(f"Salteada (sin run_info.json): {carpeta}", file=sys.stderr)
                    continue
                r = verificar_corrida(carpeta, conexion, por_tenant)
                informe.generar_corrida(carpeta)
                print(
                    f"{carpeta.name}: {len(r['trabajos'])} trabajos verificados · "
                    f"{len(r['huerfanos'])} con búsqueda de huérfanos · {len(r['errores'])} errores"
                    f" → {carpeta / ARCHIVO}"
                )
                for err in r["errores"]:
                    print(f"  ERROR {err}", file=sys.stderr)
            informe.generar_indice(Path(a.carpetas[0]).parent)
    except (ConfigError, BDError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
