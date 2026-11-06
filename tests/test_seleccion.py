"""Reglas puras de selección de ejercicio, período, período fiscal y origen (sin servidor)."""

import json

from holistor_stress.data.periodo import parsear_periodo
from holistor_stress.flows import seleccion as s
from holistor_stress.flows.gdc import hasta_primer_mes
from test_validaciones import fila

ACCESO = {
    "ejercicioSeleccionadoCodigo": 6,
    "ejercicios": [
        {"codigo": 5, "fechaDesde": "2026-01-01T00:00:00", "fechaHasta": "2026-12-31T00:00:00"},
        {"codigo": 6, "fechaDesde": "2027-01-01T00:00:00", "fechaHasta": "2027-12-31T00:00:00"},
    ],
}


def _periodos(*codigos, personalizado=None):
    lista = [{"codigo": c, "desde": f"{c[:4]}-{c[4:]}-01", "hasta": f"{c[:4]}-{c[4:]}-28"} for c in codigos]
    if personalizado:
        lista.append({"codigo": personalizado, "desde": "", "hasta": "", "personalizado": True})
    return {"periodos": lista}


# ── ejercicio ──


def test_ejercicio_que_contiene_el_primer_mes():
    ej, criterio = s.elegir_ejercicio(ACCESO, None, "202703")
    assert ej.codigo == 6 and ej.desde == "2027-01-01" and "202703" in criterio


def test_ejercicio_pedido_gana_sobre_el_periodo():
    ej, _ = s.elegir_ejercicio(ACCESO, 5, "202703")
    assert ej.codigo == 5


def test_ejercicio_todos_usa_el_preseleccionado():
    ej, criterio = s.elegir_ejercicio(ACCESO, None, None)
    assert ej.codigo == 6 and criterio == "ejercicio preseleccionado"


def test_ejercicio_inexistente():
    ej, criterio = s.elegir_ejercicio(ACCESO, None, "202501")
    assert ej is None and "202501" in criterio
    assert "5 (2026-01-01 a 2026-12-31)" in s.describir_ejercicios(ACCESO)


def test_ejercicio_con_respuesta_vacia():
    assert s.elegir_ejercicio(None, None, "202601") == (None, "ejercicio que contiene 202601")


def test_ejercicio_de_la_fila_y_de_la_plantilla_syj(tmp_path):
    assert s.ejercicio_pedido(fila(1, ejercicio=9)) == 9
    assert s.ejercicio_pedido(fila(1)) is None
    (tmp_path / "p.json").write_text(json.dumps({"Asiento_Cabecera": [{"Ejercicio": "7"}]}), encoding="utf-8")
    syj = fila(1, modulo="SYJ", plantilla="p.json", tipoLote=None)
    assert s.ejercicio_pedido(syj, tmp_path) == 7


# ── período ──


def test_meses_del_rango_sin_personalizados():
    data = _periodos("202601", "202602", "202603", personalizado="202602")
    incluidos, fuera = s.meses_del_periodo(data, parsear_periodo("202601-202602"))
    assert [p["codigo"] for p in incluidos] == ["202601", "202602"]
    assert fuera == []


def test_meses_fuera_del_ejercicio_se_informan():
    data = _periodos("202611", "202612")
    incluidos, fuera = s.meses_del_periodo(data, parsear_periodo("202611-202702"))
    assert [p["codigo"] for p in incluidos] == ["202611", "202612"]
    assert fuera == ["202701", "202702"]


def test_periodo_todos_y_orden():
    incluidos, _ = s.meses_del_periodo(_periodos("202603", "202601", "202602"), parsear_periodo("TODOS"))
    assert [p["codigo"] for p in incluidos] == ["202601", "202602", "202603"]


def test_periodo_sin_meses_en_el_ejercicio():
    assert s.meses_del_periodo(_periodos("202601"), parsear_periodo("202701")) == ([], [])


# ── período fiscal ──


def test_periodo_fiscal_por_codigo_y_empresa():
    data = {
        "items": [
            {"periodoFiscalCod": "2026-01", "periodoFiscalId": 11, "empCodigo": 99},
            {"periodoFiscalCod": "2026-01", "periodoFiscalId": 12, "empCodigo": 3064},
            {"fiscalPeriodCode": "202602", "id": 13},
        ]
    }
    assert s.buscar_periodo_fiscal_id(data, "202601", 3064) == 12
    assert s.buscar_periodo_fiscal_id(data, "202602", 3064) == 13
    assert s.buscar_periodo_fiscal_id(data, "202603", 3064) is None
    assert s.buscar_periodo_fiscal_id([{"periodoFiscalCod": "202603", "periodoFiscalId": 5}], "202603", 1) == 5


# ── origen ──


def test_origenes_solo_de_comprobantes_y_forzado():
    data = {"origenes": [{"origenAsientoId": 1, "esComprobante": True}, {"origenAsientoId": 2}]}
    assert [o["origenAsientoId"] for o in s.origenes_candidatos(data, None)] == [1]
    assert s.origenes_candidatos(data, 2) == []


def test_tipo_lote_y_tipos():
    tipos = {"tipoLote": "Compras", "tipos": [{"tipoComprobanteId": 10}, {"tipoComprobanteId": "11"}, {}]}
    assert s.coincide_tipo_lote(tipos, "COMPRAS") and not s.coincide_tipo_lote(tipos, "VENTAS")
    assert s.coincide_tipo_lote(tipos, None)
    assert s.ids_tipos_comprobante(tipos) == (10, 11)


# ── precheck ──


def test_hasta_primer_mes():
    assert hasta_primer_mes("2026-01-01T00:00:00", "2026-06-30T00:00:00") == "2026-01-31T00:00:00"
    assert hasta_primer_mes("2028-02-01T00:00:00", "2028-05-31T00:00:00") == "2028-02-29T00:00:00"
    assert hasta_primer_mes("2026-03-01", "2026-03-31") == "2026-03-31"
