"""Carga la configuración de un ambiente.

Precedencia (de mayor a menor):
1. `overrides` (argumentos de línea de comando)
2. Variables de entorno `HOLISTOR__<seccion>__<clave>` (del sistema, del CI o de `.env`)
3. `environments/<amb>.yaml`
4. Valores por defecto del modelo `Settings`
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from holistor_stress.config.settings import Settings

PREFIJO_OVERRIDE = "HOLISTOR__"
VAR_RAIZ = "HOLISTOR_STRESS_ROOT"
_NOMBRE_VALIDO = re.compile(r"^[a-z0-9_-]+$")


class ConfigError(Exception):
    """La configuración no se pudo cargar o no es válida."""


def encontrar_raiz(desde: Path | None = None, environ: Mapping[str, str] | None = None) -> Path:
    """Carpeta raíz del proyecto: HOLISTOR_STRESS_ROOT, o la primera carpeta (hacia arriba) con environments/."""
    environ = os.environ if environ is None else environ
    if environ.get(VAR_RAIZ):
        return Path(environ[VAR_RAIZ]).resolve()
    actual = (desde or Path.cwd()).resolve()
    for carpeta in (actual, *actual.parents):
        if (carpeta / "environments").is_dir():
            return carpeta
    raise ConfigError(
        f"No se encontró la carpeta 'environments/' desde {actual}. "
        f"Ejecutar desde la raíz del proyecto o definir {VAR_RAIZ}."
    )


def _merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    resultado = dict(base)
    for k, v in extra.items():
        if isinstance(v, Mapping) and isinstance(resultado.get(k), dict):
            resultado[k] = _merge(resultado[k], v)
        else:
            resultado[k] = v
    return resultado


def _overrides_de_entorno(environ: Mapping[str, str]) -> dict[str, Any]:
    """HOLISTOR__FLUJO__POLLING__INTERVALO_S=2 → {"flujo": {"polling": {"intervalo_s": 2}}}."""
    resultado: dict[str, Any] = {}
    for clave, valor in environ.items():
        if not clave.upper().startswith(PREFIJO_OVERRIDE):
            continue
        partes = [p.lower() for p in clave[len(PREFIJO_OVERRIDE) :].split("__") if p]
        if not partes:
            continue
        try:
            interpretado = yaml.safe_load(valor) if valor.strip() else ""
        except yaml.YAMLError:
            interpretado = valor
        nodo = resultado
        for p in partes[:-1]:
            nodo = nodo.setdefault(p, {})
        nodo[partes[-1]] = interpretado
    return resultado


def _formatear(err: ValidationError, origen: str) -> str:
    lineas = [f"Configuración inválida ({origen}):"]
    for e in err.errors():
        campo = ".".join(str(p) for p in e["loc"]) or "(raíz)"
        lineas.append(f"  - {campo}: {e['msg']}")
    return "\n".join(lineas)


def ambientes_disponibles(raiz: Path) -> list[str]:
    return sorted(p.stem for p in (raiz / "environments").glob("*.yaml"))


def cargar_settings(
    nombre: str,
    raiz: Path | None = None,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
    usar_dotenv: bool = True,
) -> Settings:
    nombre = (nombre or "").strip().lower()
    if not _NOMBRE_VALIDO.match(nombre):
        raise ConfigError(f"Nombre de ambiente inválido: {nombre!r} (solo letras, números, '-' y '_').")

    raiz = (raiz or encontrar_raiz(environ=environ)).resolve()
    if usar_dotenv and environ is None:
        # override=False: las variables reales del sistema/CI ganan sobre .env.
        load_dotenv(raiz / ".env", override=False)
    environ = os.environ if environ is None else environ

    archivo = raiz / "environments" / f"{nombre}.yaml"
    if not archivo.is_file():
        disponibles = ", ".join(ambientes_disponibles(raiz)) or "(ninguno)"
        raise ConfigError(f"No existe el ambiente '{nombre}' ({archivo}). Disponibles: {disponibles}.")

    try:
        contenido = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{archivo} no es un YAML válido: {e}") from e
    if not isinstance(contenido, dict):
        raise ConfigError(f"{archivo} debe contener un mapa de claves.")

    datos = _merge(contenido, _overrides_de_entorno(environ))
    if overrides:
        datos = _merge(datos, overrides)
    datos.setdefault("nombre", nombre)
    if str(datos["nombre"]).lower() != nombre:
        raise ConfigError(f"{archivo}: 'nombre: {datos['nombre']}' no coincide con el archivo ('{nombre}').")
    datos["raiz"] = raiz

    try:
        return Settings.model_validate(datos)
    except ValidationError as e:
        raise ConfigError(_formatear(e, str(archivo))) from e
