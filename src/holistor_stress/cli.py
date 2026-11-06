"""Verificación previa sin lanzar carga: holistor-stress-check --target-env qa [--users 20].

Valida configuración, guardia de producción y users.csv con los mismos módulos que usa Locust.
Códigos de salida: 0 = OK, 1 = configuración o datos inválidos, 2 = bloqueado por la guardia.
"""

from __future__ import annotations

import argparse
import sys

from holistor_stress.config import ConfigError
from holistor_stress.core.guardia import GuardiaProduccionError
from holistor_stress.core.runtime import preparar_runtime, resumen
from holistor_stress.data.users_loader import DatosInvalidosError


def _salida_utf8() -> None:
    # En Windows, si la salida va a un archivo o pipe (CI), Python usa cp1252 y rompe los acentos.
    for flujo in (sys.stdout, sys.stderr):
        if not flujo.isatty() and hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _salida_utf8()
    p = argparse.ArgumentParser(prog="holistor-stress-check", description=__doc__.splitlines()[0])
    p.add_argument("--target-env", default="qa")
    p.add_argument("--host", default=None, help="Sobrescribe base_url (se aplica la guardia igual)")
    p.add_argument("--users", type=int, default=None, help="Usuarios virtuales a correr (valida capacidad)")
    p.add_argument("--filtro-filas", default=None)
    p.add_argument("--permitir-produccion", action="store_true")
    a = p.parse_args(argv)

    try:
        rt = preparar_runtime(
            ambiente=a.target_env,
            host=a.host,
            filtro=a.filtro_filas,
            usuarios_pedidos=a.users,
            permitir_produccion=a.permitir_produccion,
        )
    except GuardiaProduccionError as e:
        print(f"BLOQUEADO: {e}", file=sys.stderr)
        return 2
    except (ConfigError, DatosInvalidosError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print("\n".join(resumen(rt)))
    print("OK: configuración y datos válidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
