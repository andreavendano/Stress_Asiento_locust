import pytest

from conftest import ENCABEZADO, fila_csv
from holistor_stress.data.users_loader import DatosInvalidosError, cargar_filas


def test_carga_con_clave_por_defecto_y_saltea_inactivas(escribir_csv):
    ruta = escribir_csv(fila_csv(1), fila_csv(2, activo="false", empresa="", periodo="mal"), "")
    r = cargar_filas(ruta, clave_por_defecto="123")
    assert [f.id for f in r.filas] == ["F1"]
    assert r.inactivas == 1
    assert r.filas[0].clave.get_secret_value() == "123"


def test_clave_de_la_fila_tiene_prioridad(escribir_csv):
    ruta = escribir_csv(fila_csv(1, clave="propia"))
    assert cargar_filas(ruta, clave_por_defecto="123").filas[0].clave.get_secret_value() == "propia"


def test_sin_clave_informa_la_variable(escribir_csv):
    ruta = escribir_csv(fila_csv(1))
    with pytest.raises(DatosInvalidosError, match="HOLISTOR_QA_CLAVE"):
        cargar_filas(ruta, nombre_var_clave="HOLISTOR_QA_CLAVE")


def test_errores_agregados_con_linea(escribir_csv):
    ruta = escribir_csv(fila_csv(1, periodo="202613"), fila_csv(2), fila_csv(3, modulo="XX"))
    with pytest.raises(DatosInvalidosError) as e:
        cargar_filas(ruta, clave_por_defecto="x")
    errores = e.value.errores
    assert len(errores) == 2
    assert "línea 2 (id F1)" in errores[0] and "periodo" in errores[0]
    assert "línea 4 (id F3)" in errores[1] and "modulo" in errores[1]


def test_bom_de_excel_y_columnas_desconocidas(proyecto):
    ruta = proyecto / "data" / "qa" / "users.csv"
    ruta.write_text("﻿" + ENCABEZADO + ",extra\n" + fila_csv(1) + ",x\n", encoding="utf-8")
    r = cargar_filas(ruta, clave_por_defecto="x")
    assert len(r.filas) == 1
    assert any("extra" in a for a in r.advertencias)


def test_faltan_columnas(proyecto):
    ruta = proyecto / "data" / "qa" / "users.csv"
    ruta.write_text("id,usuario\nF1,GDC1\n", encoding="utf-8")
    with pytest.raises(DatosInvalidosError, match="faltan las columnas"):
        cargar_filas(ruta)


def test_archivo_inexistente_sugiere_el_ejemplo(proyecto):
    (proyecto / "data" / "qa" / "users.example.csv").write_text(ENCABEZADO, encoding="utf-8")
    with pytest.raises(DatosInvalidosError, match="users.example.csv"):
        cargar_filas(proyecto / "data" / "qa" / "users.csv")
