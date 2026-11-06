import json

from holistor_stress.data import validaciones as v
from holistor_stress.data.fila import FilaCarga


def fila(n, **cambios):
    datos = {
        "id": f"F{n}",
        "tenantId": 866,
        "usuario": f"GDC{n}",
        "modulo": "GDC",
        "empresa": 3064,
        "periodo": "202601-202606",
        "tipoLote": "COMPRAS",
    }
    datos.update(cambios)
    return FilaCarga.model_validate(datos)


def test_usuario_repetido_en_el_mismo_tenant():
    errores = v.validar_usuarios_unicos([fila(1), fila(2, usuario="gdc1")])
    assert len(errores) == 1 and "sesión única" in errores[0]


def test_mismo_usuario_en_otro_tenant_es_valido():
    assert v.validar_usuarios_unicos([fila(1), fila(2, usuario="GDC1", tenantId=900)]) == []


def test_solapamiento_misma_empresa_tipo_y_meses():
    errores = v.validar_solapamientos([fila(1), fila(2, periodo="202606-202612")])
    assert len(errores) == 1 and "F1" in errores[0] and "F2" in errores[0]


def test_sin_solapamiento_si_cambia_tipo_mes_o_reemplazar():
    filas = [
        fila(1),
        fila(2, tipoLote="VENTAS"),
        fila(3, periodo="202607-202612"),
        fila(4, reemplazar=False),
        fila(5, empresa=35),
    ]
    assert v.validar_solapamientos(filas) == []


def test_todos_solapa_con_cualquier_periodo():
    assert v.validar_solapamientos([fila(1), fila(2, periodo="TODOS")])


def test_plantillas_syj(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps({"Asiento_Cabecera": [{"Empresa": 35}]}), encoding="utf-8")
    (tmp_path / "vacia.json").write_text("{}", encoding="utf-8")
    (tmp_path / "rota.json").write_text("{", encoding="utf-8")
    syj = {"modulo": "SYJ", "tipoLote": None}
    filas = [
        fila(1, **syj, plantilla="ok.json"),
        fila(2, **syj, plantilla="vacia.json"),
        fila(3, **syj, plantilla="rota.json"),
        fila(4, **syj, plantilla="no_existe.json"),
    ]
    errores = v.validar_plantillas_syj(filas, tmp_path)
    assert len(errores) == 3
    assert not any("F1" in e for e in errores)


def test_capacidad():
    filas = [fila(1), fila(2)]
    assert v.validar_capacidad(filas, 2) == []
    assert v.validar_capacidad(filas, None) == []
    assert "hay 2 filas activas y se pidieron 3" in v.validar_capacidad(filas, 3)[0]
