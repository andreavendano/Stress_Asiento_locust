"""Flujos de sesión y contexto contra el servidor simulado en memoria (sin red, sin Locust corriendo)."""

from types import SimpleNamespace

import pytest
from locust.event import Events

from holistor_stress.config.settings import Settings
from holistor_stress.core.context import ContextoAsiento
from holistor_stress.core.errores import FallaDatos, FallaHttp, SesionInvalidadaError
from holistor_stress.flows import seleccion
from holistor_stress.flows.contexto import preparar_contexto
from holistor_stress.flows.sesion import con_sesion, iniciar_sesion
from servidor_simulado import GDC, ClienteSimulado, ServidorSimulado
from test_validaciones import fila

CLAVE = "clave-super-secreta"


def settings(tmp_path, **flujo):
    return Settings.model_validate(
        {
            "nombre": "qa",
            "base_url": "https://qa.test",
            "datos": {"users_csv": "x.csv"},
            "flujo": flujo,
            "raiz": tmp_path,
        }
    )


@pytest.fixture
def armar(tmp_path):
    """armar(**cambios_fila, flujo={...}) → (usuario simulado, servidor, eventos registrados)."""

    def _armar(servidor=None, flujo=None, **cambios):
        servidor = servidor or ServidorSimulado(clave_valida=CLAVE)
        eventos = Events()
        registrados = []
        eventos.request.add_listener(lambda **kw: registrados.append(kw))
        user = SimpleNamespace(
            client=ClienteSimulado(servidor),
            ctx=ContextoAsiento(fila=fila(1, **cambios).con_clave(CLAVE)),
            settings=settings(tmp_path, **(flujo or {})),
            environment=SimpleNamespace(events=eventos),
        )
        return user, servidor, registrados

    return _armar


def test_contexto_completo_gdc(armar):
    user, srv, _ = armar(periodo="202601-202603", tipoLote="VENTAS")
    preparar_contexto(user)
    ctx = user.ctx
    assert ctx.listo and ctx.token.startswith("tok-GDC1-")
    assert ctx.ejercicio.codigo == 5
    assert ctx.periodo.meses == ("202601", "202602", "202603")
    assert ctx.periodo.fecha_desde == "2026-01-01T00:00:00" and ctx.periodo.fecha_hasta == "2026-03-31T00:00:00"
    assert ctx.periodo.periodo_fiscal_id == 71
    assert (ctx.origen.origen_asiento_id, ctx.origen.tipo_lote, ctx.origen.tipo_comprobante_ids) == (2, "VENTAS", (20,))
    assert ctx.registros_precheck == 5
    assert user.client.fallas() == []
    # Nombres de estadística "[Grupo] servicio", en el orden de la pantalla.
    nombres = [n for n, _ in user.client.respuestas]
    assert nombres == [
        "[Auth] Authenticate",
        "[GDC] acceso",
        "[GDC] periodos",
        "[GDC] GetPeriodosFiscales",
        "[GDC] origenes",
        "[GDC] tipos-comprobante",
        "[GDC] tipos-comprobante",
        "[GDC] precheck-estructura",
    ]


def test_sin_precheck_y_precheck_off(armar):
    user, _, _ = armar()
    preparar_contexto(user, con_precheck=False)
    assert user.ctx.listo and user.ctx.registros_precheck is None
    user, _, _ = armar(flujo={"precheck": "off"})
    preparar_contexto(user)
    assert user.ctx.registros_precheck is None


def test_precheck_primer_mes_vacio_consulta_el_rango_completo(armar):
    srv = ServidorSimulado(clave_valida=CLAVE, registros_precheck=0)
    user, _, _ = armar(servidor=srv)
    with pytest.raises(FallaDatos, match=r"\[GDC1 · E3064 · 202601-202606 · COMPRAS\] lote sin comprobantes"):
        preparar_contexto(user)
    assert srv.llamadas.count(("POST", f"{GDC}/precheck-estructura")) == 2


def test_clave_rechazada_es_falla_de_datos_y_no_se_filtra(armar):
    user, _, _ = armar()
    user.ctx = ContextoAsiento(fila=user.ctx.fila.con_clave("clave-incorrecta-123"))
    with pytest.raises(FallaDatos, match="revisar usuario, clave y tenant") as e:
        iniciar_sesion(user)
    assert user.ctx.token is None
    textos = [str(e.value), *user.client.fallas()]
    assert all("clave-incorrecta-123" not in t for t in textos)


def test_empresa_sin_ejercicio_marca_falla_en_acceso(armar):
    user, _, _ = armar(periodo="202501")
    with pytest.raises(FallaDatos, match="no tiene ejercicio que contiene 202501"):
        preparar_contexto(user)
    nombre, resp = user.client.respuestas[-1]
    assert nombre == "[GDC] acceso" and "[GDC1 · E3064 · 202501 · COMPRAS]" in resp.resultado


def test_periodo_fuera_del_ejercicio_pedido(armar):
    user, _, _ = armar(periodo="202701", ejercicio=5)
    with pytest.raises(FallaDatos, match="fuera del ejercicio 5"):
        preparar_contexto(user)


def test_tipo_lote_sin_origen(armar):
    user, _, _ = armar(tipoLote="CERTIFICADOS_EMITIDOS")
    with pytest.raises(FallaDatos, match="no hay origen activo de comprobantes para CERTIFICADOS_EMITIDOS"):
        preparar_contexto(user)


def test_periodo_fiscal_respaldo(armar, monkeypatch):
    monkeypatch.setattr(seleccion, "buscar_periodo_fiscal_id", lambda *a: None)
    user, _, _ = armar(periodoFiscalId=44)
    preparar_contexto(user)
    assert user.ctx.periodo.periodo_fiscal_id == 44
    user, _, _ = armar()
    preparar_contexto(user)
    assert user.ctx.periodo.periodo_fiscal_id == 1  # flujo.periodo_fiscal_id_defecto
    user, _, _ = armar(flujo={"periodo_fiscal_id_defecto": None})
    with pytest.raises(FallaDatos, match="no hay respaldo"):
        preparar_contexto(user)


def test_5xx_es_falla_transitoria(armar):
    srv = ServidorSimulado(clave_valida=CLAVE, fallar={f"{GDC}/periodos": 500})
    user, _, _ = armar(servidor=srv)
    with pytest.raises(FallaHttp, match="HTTP 500") as e:
        preparar_contexto(user)
    assert not isinstance(e.value, FallaDatos)
    preparar_contexto(user)  # la siguiente iteración funciona
    assert user.ctx.listo


def test_401_relogin_y_reintento(armar):
    user, srv, eventos = armar()
    iniciar_sesion(user)
    srv.invalidar_sesion("GDC1")  # alguien inició sesión con GDC1 en otro lado
    data = con_sesion(user, seleccion.seleccionar_empresa_ejercicio, user)
    assert data.codigo == 5
    assert [e["name"] for e in eventos] == ["[Sesión] re-login por 401"]
    assert eventos[0]["exception"] is None


def test_401_persistente_es_sesion_invalidada(armar):
    user, srv, eventos = armar()
    iniciar_sesion(user)

    def paso_que_pierde_la_sesion():
        srv.invalidar_sesion("GDC1")
        return seleccion.seleccionar_empresa_ejercicio(user)

    with pytest.raises(SesionInvalidadaError, match=r"¿usuario usado en otra sesión\?"):
        con_sesion(user, paso_que_pierde_la_sesion)
    assert [e["name"] for e in eventos] == ["[Sesión] re-login por 401", "[Sesión] sesión invalidada"]


def test_precheck_completo_consulta_todo_el_rango_en_una_llamada(armar):
    user, srv, _ = armar(flujo={"precheck": "completo"})
    enviados = []
    original = srv.responder

    def espiar(metodo, ruta, params, body, headers):
        if ruta.endswith("precheck-estructura"):
            enviados.append(body)
        return original(metodo, ruta, params, body, headers)

    srv.responder = espiar
    preparar_contexto(user)
    assert len(enviados) == 1
    assert enviados[0]["fechaDesde"] == "2026-01-01T00:00:00"
    assert enviados[0]["fechaHasta"] == "2026-06-30T00:00:00"  # último mes del rango, no el primero
    assert user.ctx.registros_precheck == 5
