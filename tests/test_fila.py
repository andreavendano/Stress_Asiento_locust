import pytest
from pydantic import ValidationError

from holistor_stress.data.fila import FilaCarga

BASE = {
    "id": "F1",
    "tenantId": "866",
    "usuario": "GDC1",
    "clave": "secreta",
    "modulo": "gdc",
    "empresa": "3064",
    "periodo": "202601-202606",
    "tipoLote": "compras",
}


def test_normaliza_y_aplica_defaults():
    f = FilaCarga.model_validate({**BASE, "reemplazar": "", "activo": ""})
    assert f.modulo == "GDC" and f.tipo_lote == "COMPRAS"
    assert f.activo is True
    assert f.reemplazar is None and f.reemplazar_efectivo is True
    assert f.comprobantes_a_incluir == "Todos"


def test_etiqueta_igual_a_la_coleccion():
    assert FilaCarga.model_validate(BASE).etiqueta == "[GDC1 · E3064 · 202601-202606 · COMPRAS]"


def test_clave_no_se_expone():
    f = FilaCarga.model_validate(BASE)
    assert "secreta" not in repr(f) and "secreta" not in str(f.model_dump())
    assert f.clave.get_secret_value() == "secreta"


def test_gdc_sin_tipo_lote_ni_origen():
    with pytest.raises(ValidationError, match="GDC requiere"):
        FilaCarga.model_validate({**BASE, "tipoLote": ""})


def test_gdc_con_origen_sin_tipo_lote():
    assert FilaCarga.model_validate({**BASE, "tipoLote": "", "origenAsientoId": "4"}).origen_asiento_id == 4


def test_syj_requiere_plantilla():
    with pytest.raises(ValidationError, match="SYJ requiere"):
        FilaCarga.model_validate({**BASE, "modulo": "SYJ", "tipoLote": ""})


def test_syj_reemplazar_vacio_respeta_json():
    f = FilaCarga.model_validate({**BASE, "modulo": "SYJ", "tipoLote": "", "plantilla": "a.json"})
    assert f.reemplazar_efectivo is None


@pytest.mark.parametrize(("campo", "valor"), [("tipoLote", "OTRO"), ("modulo", "XYZ"), ("periodo", "2026")])
def test_valores_invalidos(campo, valor):
    with pytest.raises(ValidationError):
        FilaCarga.model_validate({**BASE, campo: valor})
