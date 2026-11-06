import pytest

from holistor_stress.data.periodo import parsear_periodo


@pytest.mark.parametrize(
    ("texto", "desde", "hasta"),
    [
        ("202601", "202601", "202601"),
        ("202601-202606", "202601", "202606"),
        (" 202601 - 202606 ", "202601", "202606"),
        ("202601202606", "202601", "202606"),
    ],
)
def test_formatos_validos(texto, desde, hasta):
    r = parsear_periodo(texto)
    assert (r.desde, r.hasta) == (desde, hasta)


def test_todos():
    r = parsear_periodo("todos")
    assert r.todos and r.meses() is None and str(r) == "TODOS"


def test_meses_cruzan_el_anio():
    assert parsear_periodo("202611-202702").meses() == ["202611", "202612", "202701", "202702"]


@pytest.mark.parametrize("texto", ["2026-01", "202613", "202600", "202606-202601", "", "ENERO"])
def test_formatos_invalidos(texto):
    with pytest.raises(ValueError):
        parsear_periodo(texto)


def test_solapamiento():
    a = parsear_periodo("202601-202606")
    assert a.solapa(parsear_periodo("202606-202612"))
    assert not a.solapa(parsear_periodo("202607-202612"))
    assert a.solapa(parsear_periodo("TODOS"))
