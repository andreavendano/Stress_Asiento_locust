from __future__ import annotations

from pathlib import Path

import pytest

ENCABEZADO = "id,activo,tenantId,usuario,clave,modulo,empresa,periodo,tipoLote,reemplazar,plantilla"

YAML_MINIMO = """\
nombre: qa
base_url: "https://qa.ejemplo.test/"
datos:
  users_csv: "data/qa/users.csv"
  clave_env_var: "HOLISTOR_QA_CLAVE"
"""


def fila_csv(n: int, **cambios: str) -> str:
    valores = {
        "id": f"F{n}",
        "activo": "true",
        "tenantId": "866",
        "usuario": f"GDC{n}",
        "clave": "",
        "modulo": "GDC",
        "empresa": str(3000 + n),
        "periodo": "202601-202606",
        "tipoLote": "COMPRAS",
        "reemplazar": "true",
        "plantilla": "",
    }
    valores.update(cambios)
    return ",".join(valores[c] for c in ENCABEZADO.split(","))


@pytest.fixture
def proyecto(tmp_path: Path):
    """Proyecto mínimo en disco: environments/qa.yaml + data/qa/users.csv."""
    (tmp_path / "environments").mkdir()
    (tmp_path / "environments" / "qa.yaml").write_text(YAML_MINIMO, encoding="utf-8")
    (tmp_path / "data" / "qa").mkdir(parents=True)
    (tmp_path / "data" / "plantillas" / "syj").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def escribir_csv(proyecto: Path):
    """Escribe data/qa/users.csv del proyecto mínimo con el encabezado estándar."""

    def _escribir(*filas: str) -> Path:
        ruta = proyecto / "data" / "qa" / "users.csv"
        ruta.write_text("\n".join([ENCABEZADO, *filas]) + "\n", encoding="utf-8")
        return ruta

    return _escribir
