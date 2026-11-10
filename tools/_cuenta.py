"""Cuenta de las herramientas sueltas: la primera fila IMPO con login=plataforma de data/qa/users.csv.

Devuelve las mismas claves que leían del viejo accounts_QA.csv: tenancy, username, password, tenant_id.
La clave sale de la columna `clave` o, si viene vacía, de HOLISTOR_QA_CLAVE (.env).
"""

import csv
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def cuenta(indice: int = 0, modulo: str = "IMPO") -> dict:
    ruta = Path(os.getenv("HOLISTOR__DATOS__USERS_CSV") or RAIZ / "data" / "qa" / "users.csv")
    if not ruta.is_absolute():
        ruta = RAIZ / ruta
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        filas = [r for r in csv.DictReader(f)
                 if (r.get("modulo") or "").strip().upper() == modulo and (r.get("login") or "").strip() == "plataforma"
                 and (r.get("activo") or "true").strip().lower() not in ("false", "0", "no", "n")]
    if len(filas) <= indice:
        raise SystemExit(f"{ruta}: no hay una fila {modulo} con login=plataforma número {indice + 1}")
    r = filas[indice]
    return {"tenancy": r["tenancy"], "username": r["usuario"], "tenant_id": r["tenantId"],
            "password": (r.get("clave") or "").strip() or os.getenv("HOLISTOR_QA_CLAVE", "")}
