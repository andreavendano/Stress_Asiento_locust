import pytest

from conftest import fila_csv
from holistor_stress.config import ConfigError, cargar_settings
from holistor_stress.core.guardia import GuardiaProduccionError
from holistor_stress.core.runtime import preparar_runtime
from holistor_stress.data.users_loader import DatosInvalidosError

ENV = {"HOLISTOR_QA_CLAVE": "123"}


def test_carga_yaml_con_defaults(proyecto):
    s = cargar_settings("qa", raiz=proyecto, environ={})
    assert s.base_url == "https://qa.ejemplo.test"  # sin barra final
    assert s.flujo.polling.intervalo_s == 3
    assert s.ruta(s.datos.users_csv) == proyecto / "data" / "qa" / "users.csv"


def test_variables_de_entorno_y_overrides(proyecto):
    environ = {"HOLISTOR__FLUJO__POLLING__INTERVALO_S": "1.5", "HOLISTOR__BASE_URL": "https://otro.test"}
    s = cargar_settings("qa", raiz=proyecto, environ=environ, overrides={"base_url": "https://cli.test"})
    assert s.flujo.polling.intervalo_s == 1.5
    assert s.base_url == "https://cli.test"  # la CLI gana sobre la variable de entorno


def test_ambiente_inexistente_lista_los_disponibles(proyecto):
    with pytest.raises(ConfigError, match="Disponibles: qa"):
        cargar_settings("staging", raiz=proyecto, environ={})


def test_nombre_con_path_traversal(proyecto):
    with pytest.raises(ConfigError, match="inválido"):
        cargar_settings("../qa", raiz=proyecto, environ={})


def test_error_de_tipeo_en_el_yaml(proyecto):
    with pytest.raises(ConfigError, match="flujo.polling.intervalo"):
        cargar_settings("qa", raiz=proyecto, environ={"HOLISTOR__FLUJO__POLLING__INTERVALO": "2"})


def test_runtime_completo(proyecto, escribir_csv):
    escribir_csv(fila_csv(1), fila_csv(2), fila_csv(3, modulo="SYJ", tipoLote="", plantilla="x.json"))
    rt = preparar_runtime("qa", raiz=proyecto, environ=ENV)
    assert [f.id for f in rt.datos.filas] == ["F1", "F2"]  # SYJ deshabilitado por defecto
    assert rt.datos.excluidas_por_modulo == 1
    assert rt.pool.total == 2
    assert rt.run.run_id.startswith("qa-")


def test_runtime_filtro_y_capacidad(proyecto, escribir_csv):
    escribir_csv(fila_csv(1), fila_csv(2, tipoLote="VENTAS"))
    rt = preparar_runtime("qa", raiz=proyecto, environ=ENV, filtro="tipoLote=ventas")
    assert [f.id for f in rt.datos.filas] == ["F2"]
    with pytest.raises(DatosInvalidosError, match="se pidieron 3"):
        preparar_runtime("qa", raiz=proyecto, environ=ENV, usuarios_pedidos=3)
    with pytest.raises(DatosInvalidosError, match="campo desconocido"):
        preparar_runtime("qa", raiz=proyecto, environ=ENV, filtro="noexiste=1")


def test_guardia_de_produccion(proyecto, escribir_csv):
    escribir_csv(fila_csv(1))
    environ = {**ENV, "HOLISTOR__URLS_PRODUCCION": "[https://prod.test]"}
    with pytest.raises(GuardiaProduccionError, match="PRODUCCIÓN"):
        preparar_runtime("qa", raiz=proyecto, environ=environ, host="https://prod.test/")
    rt = preparar_runtime("qa", raiz=proyecto, environ=environ, host="https://prod.test", permitir_produccion=True)
    assert rt.base_url == "https://prod.test"
