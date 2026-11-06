"""Verificación en base: guardia de solo SELECT, configuración y unión con los trabajos (sin base real)."""

import json

import pytest

from holistor_stress.bd.conexion import BDError, ConfigBD, solo_select
from holistor_stress.bd.verificacion import verificar_corrida
from holistor_stress.config.settings import Settings
from holistor_stress.reporting import informe
from test_reporting import _corrida


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  -- comentario\nselect COUNT(*) FROM t WHERE x IN ('a', 'b')",
        "SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT')",  # 'INSERT' es un literal
        "WITH c AS (SELECT 1 AS n) SELECT n FROM c",
        "SELECT 1;",
    ],
)
def test_select_permitido(sql):
    assert solo_select(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM nuc_AsientosOtrosModulos",
        "UPDATE t SET a = 1",
        "SELECT 1; DROP TABLE t",
        "SELECT * INTO copia FROM t",
        "/* SELECT */ TRUNCATE TABLE t",
        "SELECT 1 EXEC sp_who",
        "EXEC xp_cmdshell 'dir'",
    ],
)
def test_escritura_rechazada(sql):
    with pytest.raises(BDError):
        solo_select(sql)


def _settings(tmp_path, **bd):
    return Settings.model_validate(
        {
            "nombre": "qa",
            "base_url": "https://qa.test",
            "datos": {"users_csv": "x"},
            "raiz": tmp_path,
            "bd": {"habilitada": True, **bd},
        }  # fmt: skip
    )


def test_config_desde_variables_sin_exponer_la_clave(tmp_path):
    env = {"HOLISTOR_QA_DB_SERVIDOR": "srv,1433", "HOLISTOR_QA_DB_BASE": "base", "HOLISTOR_QA_DB_USUARIO": "u",
           "HOLISTOR_QA_DB_CLAVE": "p}a;ss"}  # fmt: skip
    cfg = ConfigBD.desde(_settings(tmp_path), env)
    assert "PWD={p}}a;ss}" in cfg.cadena() and "ApplicationIntent=ReadOnly" in cfg.cadena()
    assert "p}a;ss" not in repr(cfg)
    assert cfg.ocultar("Login failed: p}a;ss") == "Login failed: ***"


def test_config_incompleta_o_deshabilitada(tmp_path):
    with pytest.raises(BDError, match="HOLISTOR_QA_DB_CLAVE"):
        ConfigBD.desde(_settings(tmp_path), {"HOLISTOR_QA_DB_SERVIDOR": "s", "HOLISTOR_QA_DB_BASE": "b",
                                             "HOLISTOR_QA_DB_USUARIO": "u"})  # fmt: skip
    with pytest.raises(BDError, match="deshabilitada"):
        ConfigBD.desde(_settings(tmp_path, habilitada=False), {})


class ConexionFalsa:
    """Responde como la base: los trabajos por GUID y los huérfanos por empresa / tipo / período."""

    class cfg:  # noqa: N801
        base = "z_qa_test"

    def __init__(self):
        self.consultas = []

    def consultar(self, sql):
        solo_select(sql)
        self.consultas.append(sql)
        if "AS asientos_ok_control" in sql:
            return ["fila", "asientos_ok_control", "comprobantes_contabilizados"], [("F0", 6, 1200)]
        if sql.startswith("SELECT AsientoFechaCreacion"):
            return ["AsientoFechaCreacion", "AsientosStatus", "AsientosID"], [("2026-11-05 18:42:34", "OK", "x")] * 6
        return ["comprobantes_contabilizados"], [(15404,)]


def test_verificacion_se_une_al_informe(tmp_path):
    carpeta = _corrida(tmp_path / "reports" / "run1", trabajos=((3.0, 1.0, "OK"), (5.0, 2.0, "FALLA")))
    # trabajo 0 con IDs de asiento; trabajo 1 falló sin requestId (como el timeout de generar)
    contenido = (carpeta / "trabajos.csv").read_text(encoding="utf-8-sig").splitlines()
    cab = contenido[0].split(";")
    filas = [dict(zip(cab, linea.split(";"), strict=False)) for linea in contenido[1:]]
    filas[0].update(tipo_lote="COMPRAS", comprobantes_lote="1200", ids_asientos="9e21bc98-0d69-4ef3-bb0e-07799e3790df",
                    request_id="r1", asientos_total="6")  # fmt: skip
    filas[1].update(tipo_lote="VENTAS", request_id="", fecha_desde="2027-01-01", fecha_hasta="2027-06-30")
    (carpeta / "trabajos.csv").write_text(
        "﻿" + "\n".join([";".join(cab)] + [";".join(f.get(c, "") for c in cab) for f in filas]) + "\n",
        encoding="utf-8",
    )
    if "comprobantes_lote" not in cab:
        pytest.skip("trabajos.csv de prueba sin columna comprobantes_lote")

    r = verificar_corrida(carpeta, ConexionFalsa())
    assert r["trabajos"]["F0|2026-11-05T10:00:00"] == {"asientos_ok_control": 6, "comprobantes_contabilizados": 1200}
    assert r["huerfanos"]["F1|2026-11-05T10:01:00"]["comprobantes_contabilizados"] == 15404
    assert json.loads((carpeta / "verificacion_resultado.json").read_text(encoding="utf-8"))["base"] == "z_qa_test"

    resumen = informe.generar_corrida(carpeta)
    vb = resumen["verificacion_bd"]
    assert (vb["verificados"], vb["coinciden"]) == (1, 1)
    assert vb["huerfanos"][0]["bd_asientos"] == 6
    html = (carpeta / "reporte.html").read_text(encoding="utf-8")
    assert "Verificación en la base" in html and "sí creó" in html
    assert "1 de 1 trabajos coinciden" in (carpeta / "resumen.md").read_text(encoding="utf-8")


def test_varios_trabajos_por_fila_solo_se_verifica_el_ultimo():
    from datetime import UTC, datetime

    from holistor_stress.reporting.sql_verificacion import consultas, ultimos_por_fila

    guid = "9e21bc98-0d69-4ef3-bb0e-07799e3790df"
    base = {"fila": "F1", "usuario": "GDC1", "empresa": "3064", "tipo_lote": "COMPRAS", "asientos_total": "6",
            "fecha_desde": "2026-01-01", "fecha_hasta": "2026-06-30"}  # fmt: skip
    detalle = [
        {**base, "inicio": "2026-11-05T10:00:00", "resultado": "OK", "request_id": "r1", "ids_asientos": guid},
        {**base, "inicio": "2026-11-05T10:01:00", "resultado": "FALLA", "request_id": ""},
        {**base, "inicio": "2026-11-05T10:02:00", "resultado": "OK", "request_id": "r3", "ids_asientos": guid},
    ]
    ultimos, siguiente = ultimos_por_fila(detalle)
    assert ultimos == {"F1|2026-11-05T10:02:00"}
    assert siguiente["F1|2026-11-05T10:01:00"] == "2026-11-05T10:02:00"
    lista = consultas({"trabajos": {"detalle": detalle}})
    assert [(c.tipo, c.clave) for c in lista] == [
        ("huerfanos", "F1|2026-11-05T10:01:00"),
        ("huerfanos_comprobantes", "F1|2026-11-05T10:01:00"),
        ("trabajo", "F1|2026-11-05T10:02:00"),
    ]
    # ventana del huérfano en UTC: desde su inicio hasta el inicio del siguiente trabajo de la fila
    utc = lambda s: datetime.fromisoformat(s).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")  # noqa: E731
    assert (
        f">= '{utc('2026-11-05T10:01:00')}' AND AsientoFechaCreacion < '{utc('2026-11-05T10:02:00')}'" in lista[0].sql
    )


def test_verificacion_multitenant_consulta_la_base_de_cada_tenant(tmp_path):
    carpeta = _corrida(tmp_path / "reports" / "run1", trabajos=((3.0, 1.0, "OK"), (5.0, 2.0, "OK")))
    contenido = (carpeta / "trabajos.csv").read_text(encoding="utf-8-sig").splitlines()
    cab = contenido[0].split(";")
    filas = [dict(zip(cab, linea.split(";"), strict=False)) for linea in contenido[1:]]
    for f, tenant, guid in ((filas[0], "866", "9e21bc98-0d69-4ef3-bb0e-07799e3790df"),
                            (filas[1], "867", "1e21bc98-0d69-4ef3-bb0e-07799e3790df")):  # fmt: skip
        f.update(tenant=tenant, tipo_lote="COMPRAS", ids_asientos=guid, request_id="r", asientos_total="1")
    (carpeta / "trabajos.csv").write_text(
        "\n".join([";".join(cab)] + [";".join(f.get(c, "") for c in cab) for f in filas]) + "\n", encoding="utf-8"
    )
    if "tenant" not in cab:
        pytest.skip("trabajos.csv de prueba sin columna tenant")

    class Otra(ConexionFalsa):
        class cfg:  # noqa: N801
            base = "z_qa_otro"

    principal, otra = ConexionFalsa(), Otra()
    r = verificar_corrida(carpeta, principal, {"867": otra})
    assert len(principal.consultas) == 1 and len(otra.consultas) == 1
    assert "9e21bc98" in principal.consultas[0] and "1e21bc98" in otra.consultas[0]
    assert r["bases"] == {"866": "z_qa_test", "867": "z_qa_otro"} and r["base"] == "z_qa_otro, z_qa_test"
