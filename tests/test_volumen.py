"""Volumen de comprobantes (listado .xlsx → CSV), comprobantes_lote y verificacion.sql."""

import csv
import zipfile

from holistor_stress.data.volumen import Volumen, importar_listado, main, meses_entre
from holistor_stress.reporting.informe import completar_volumen
from holistor_stress.reporting.sql_verificacion import generar_sql

HOJA = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c>
<c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c><c r="F1" t="s"><v>5</v></c></row>
<row r="2"><c r="A2"><v>3065</v></c><c r="B2"><v>202701</v></c><c r="C2"><v>1500</v></c><c r="D2"><v>2580</v></c>
<c r="F2" t="inlineStr"><is><t>GDC1</t></is></c></row>
<row r="3"><c r="A3"><v>3065</v></c><c r="B3"><v>202702</v></c><c r="C3"><v>1500</v></c><c r="D3"><v>2561</v></c>
<c r="E3"><v>3</v></c></row>
</sheetData></worksheet>"""
COMPARTIDAS = (
    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    + "".join(
        f"<si><t>{t}</t></si>"
        for t in ("EmpCodigo ", "PeriodosCod ", "Compras", "Ventas ", "Certificados ", "Usuarios")
    )
    + "</sst>"
)
LIBRO = (
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets></workbook>'
)
RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
)


def _xlsx(ruta):
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("xl/workbook.xml", LIBRO)
        z.writestr("xl/_rels/workbook.xml.rels", RELS)
        z.writestr("xl/sharedStrings.xml", COMPARTIDAS)
        z.writestr("xl/worksheets/sheet1.xml", HOJA)
    return ruta


def test_importa_el_listado_con_encabezados_con_espacios(tmp_path):
    filas = importar_listado(_xlsx(tmp_path / "listado.xlsx"))
    assert filas == [
        {"empresa": 3065, "periodo": "202701", "compras": 1500, "ventas": 2580, "certificados": 0},
        {"empresa": 3065, "periodo": "202702", "compras": 1500, "ventas": 2561, "certificados": 3},
    ]


def test_cli_y_suma_por_tipo_y_meses(tmp_path):
    salida = tmp_path / "volumen.csv"
    assert main([str(_xlsx(tmp_path / "l.xlsx")), "--salida", str(salida)]) == 0
    v = Volumen.desde_csv(salida)
    assert v.comprobantes(3065, "VENTAS", ["202701", "202702"]) == 5141
    assert v.comprobantes(3065, "compras", ("202701",)) == 1500
    assert v.comprobantes(3065, "CERTIFICADOS_EMITIDOS", ["202702"]) == 3
    assert v.comprobantes(3065, "VENTAS", ["202703"]) is None  # mes fuera del listado
    assert v.comprobantes(99, "VENTAS", ["202701"]) is None


def test_meses_entre():
    assert meses_entre("2026-11-01", "2027-02-28") == ["202611", "202612", "202701", "202702"]


def _trabajos(carpeta, filas):
    carpeta.mkdir()
    columnas = ["inicio", "fila", "usuario", "empresa", "fecha_desde", "fecha_hasta", "tipo_lote",
                "comprobantes_precheck", "request_id", "asientos_total", "resultado", "errores",
                "ids_asientos"]  # fmt: skip
    with (carpeta / "trabajos.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, delimiter=";")
        w.writeheader()
        w.writerows(filas)


def test_completa_comprobantes_lote_en_corridas_anteriores(tmp_path):
    v = Volumen({(3065, "202701"): {"compras": 1500, "ventas": 2580, "certificados": 0},
                 (3065, "202702"): {"compras": 1500, "ventas": 2561, "certificados": 0}})  # fmt: skip
    base = {"empresa": "3065", "fecha_desde": "2027-01-01", "fecha_hasta": "2027-02-28", "resultado": "OK"}
    _trabajos(
        tmp_path / "run",
        [{**base, "tipo_lote": "VENTAS"}, {**base, "tipo_lote": "COMPRAS", "fecha_hasta": "2027-03-31"}],
    )
    assert completar_volumen(tmp_path / "run", v) == 1
    with (tmp_path / "run" / "trabajos.csv").open(encoding="utf-8-sig") as f:
        lector = csv.DictReader(f, delimiter=";")
        filas = list(lector)
    assert lector.fieldnames.index("comprobantes_lote") == lector.fieldnames.index("comprobantes_precheck") + 1
    assert [f["comprobantes_lote"] for f in filas] == ["5141", ""]  # 202703 no está en el listado


def test_sql_por_trabajo_y_huerfanos():
    guid = "9e21bc98-0d69-4ef3-bb0e-07799e3790df"
    resumen = {
        "run_id": "qa-1",
        "escenario_desc": "GDC",
        "ambiente": "qa",
        "inicio": "2026-11-05T15:41:05",
        "fin": "",
        "trabajos": {
            "detalle": [
                {
                    "fila": "F1",
                    "usuario": "GDC1",
                    "empresa": "3064",
                    "tipo_lote": "COMPRAS",
                    "asientos_total": "1",
                    "comprobantes_lote": "1200",
                    "ids_asientos": guid,
                    "resultado": "OK",
                    "request_id": "r1",
                },
                {
                    "fila": "F8",
                    "usuario": "GDC8",
                    "empresa": "3065",
                    "tipo_lote": "VENTAS",
                    "resultado": "FALLA",
                    "request_id": "",
                    "fecha_desde": "2027-01-01",
                    "fecha_hasta": "2027-06-30",
                    "inicio": "2026-11-05T15:41:37",
                    "errores": "sin respuesta: ReadTimeout",
                },
            ]  # fmt: skip
        },
    }
    sql = generar_sql(resumen)
    assert f"CCpraContabilizado = 1 AND CCpraGUIDAsiento IN ('{guid}')" in sql
    assert f"AsientosStatus = 'OK' AND AsientosID IN ('{guid}')" in sql
    assert "1200 AS comprobantes_esperados" in sql
    assert "AsientosEmpresa = 3065" in sql and "LIKE 'Resumen Ventas%'" in sql
    assert "CVtaContabilizado = 1 AND CVtaGUIDAsiento IN (" in sql
    assert generar_sql({"trabajos": None}) is None
