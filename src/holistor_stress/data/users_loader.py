"""Lectura de users.csv con errores agregados por línea (se informan todos juntos, no de a uno)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from holistor_stress.data.fila import FilaCarga

COLUMNAS_OBLIGATORIAS = ("id", "tenantId", "usuario", "modulo", "empresa", "periodo")
# Columnas que la colección de Postman admite y Locust todavía no usa: se aceptan sin advertencia.
COLUMNAS_IGNORADAS = {"asientosJson"}


class DatosInvalidosError(Exception):
    def __init__(self, errores: list[str]):
        self.errores = errores
        super().__init__("Datos inválidos:\n" + "\n".join(f"  - {e}" for e in errores))


@dataclass
class ResultadoCarga:
    filas: list[FilaCarga]
    inactivas: int = 0
    advertencias: list[str] = field(default_factory=list)


def _columnas_conocidas() -> set[str]:
    conocidas = set()
    for nombre, info in FilaCarga.model_fields.items():
        conocidas.add(info.alias or nombre)
    return conocidas


def _es_inactiva(valor: str | None) -> bool:
    return str(valor or "").strip().lower() in {"false", "0", "no", "n"}


def cargar_filas(
    ruta: Path, clave_por_defecto: str | None = None, nombre_var_clave: str | None = None
) -> ResultadoCarga:
    if not ruta.is_file():
        ejemplo = ruta.with_name(ruta.stem + ".example" + ruta.suffix)
        pista = f" Copiar {ejemplo.name} como {ruta.name}." if ejemplo.is_file() else ""
        raise DatosInvalidosError([f"No existe el archivo de datos {ruta}.{pista}"])

    errores: list[str] = []
    advertencias: list[str] = []
    filas: list[FilaCarga] = []
    sin_clave: list[str] = []
    inactivas = 0

    # utf-8-sig: tolera el BOM que agrega Excel al guardar como CSV.
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        encabezado = [c.strip() for c in (lector.fieldnames or [])]
        faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in encabezado]
        if faltan:
            raise DatosInvalidosError([f"{ruta.name}: faltan las columnas {', '.join(faltan)}"])
        desconocidas = set(encabezado) - _columnas_conocidas() - COLUMNAS_IGNORADAS
        if desconocidas:
            advertencias.append(f"{ruta.name}: columnas no reconocidas (se ignoran): {', '.join(sorted(desconocidas))}")

        for crudo in lector:
            linea = lector.line_num
            registro = {(k or "").strip(): v for k, v in crudo.items() if k}
            if not any((v or "").strip() for v in registro.values()):
                continue  # línea en blanco
            if _es_inactiva(registro.get("activo")):
                inactivas += 1
                continue
            ref = f"{ruta.name} línea {linea} (id {registro.get('id') or '?'})"
            try:
                fila = FilaCarga.model_validate(registro)
            except ValidationError as e:
                for err in e.errors():
                    campo = ".".join(str(p) for p in err["loc"]) or "fila"
                    msg = err["msg"].removeprefix("Value error, ")
                    errores.append(f"{ref}: {campo}: {msg}")
                continue
            if fila.clave is None:
                if not clave_por_defecto:
                    sin_clave.append(fila.id)
                    continue
                fila = fila.con_clave(clave_por_defecto)
            filas.append(fila)

    if sin_clave:
        var = f"la variable de entorno {nombre_var_clave}" if nombre_var_clave else "una clave por defecto"
        muestra = ", ".join(sin_clave[:5]) + (f" y {len(sin_clave) - 5} más" if len(sin_clave) > 5 else "")
        errores.append(
            f"{ruta.name}: {len(sin_clave)} filas sin clave ({muestra}): la columna 'clave' está vacía "
            f"y {var} no está definida (definirla en .env o en el sistema)"
        )
    if errores:
        raise DatosInvalidosError(errores)
    return ResultadoCarga(filas=filas, inactivas=inactivas, advertencias=advertencias)
