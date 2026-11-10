"""Escenarios de comprobantes (importación, modificación masiva, crear comprobante) contra el servidor simulado."""

import csv
import string
from types import SimpleNamespace

import pytest
from locust.event import Events
from pydantic import ValidationError

from holistor_stress.api.comprobantes import extraer_id_comprobante
from holistor_stress.config.settings import Settings
from holistor_stress.core.contexto_comprobantes import ContextoComprobantes
from holistor_stress.core.errores import FallaDatos, SesionInvalidadaError
from holistor_stress.data import validaciones as v
from holistor_stress.data.fila import FilaCarga
from holistor_stress.data.preparacion import preparar_datos
from holistor_stress.flows import maestros
from holistor_stress.flows import pasos_comprobante_completo as pasos
from holistor_stress.flows.comprobante import ComprobanteCompleto, ComprobanteLite, cuerpo_comprobante
from holistor_stress.flows.importacion import Importacion, generar_csv, monto, multipart
from holistor_stress.flows.modificacion import ModificacionMasiva
from holistor_stress.flows.sesion import con_sesion
from holistor_stress.reporting.ciclos import RegistroCiclos
from servidor_comprobantes import ClienteComprobantes, ServidorComprobantes

PLANTILLA = "data/plantillas/importacion/plantilla_importacion_compras_oficial.csv"


def fila_c(modulo="IMPO", **cambios) -> FilaCarga:
    datos = {"id": f"F-{modulo}", "tenantId": 867, "usuario": "admin", "modulo": modulo, "empresa": 6,
             "periodo": "202601", "login": "plataforma", "tenancy": "GDCpruebasQA7", **cambios}  # fmt: skip
    return FilaCarga.model_validate(datos)


@pytest.fixture(autouse=True)
def _sin_cache():
    maestros.limpiar_cache()
    yield
    maestros.limpiar_cache()


@pytest.fixture
def armar(tmp_path):
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]

    def _armar(modulo="IMPO", servidor=None, settings_extra=None, preparar=True, **cambios):
        datos = {
            "nombre": "qa",
            "base_url": "https://back.test",
            "datos": {"users_csv": "x"},
            "plataforma": {"host_url": "https://plat.test", "portal_url": "https://portal.test",
                           "front_url": "https://front.test"},
            "importacion": {"origen_codigo": "PIC", "tipo_comprobante": "11", "moneda": "PES", "tipo_cambio": 1,
                            "importe_min": 100, "importe_max": 200, "lote_n": 5, "intervalo_sondeo_s": 0.001,
                            "plantilla": str(raiz / PLANTILLA)},
            "raiz": raiz,
            **(settings_extra or {}),
        }  # fmt: skip
        settings = Settings.model_validate(datos)
        srv = servidor or ServidorComprobantes()
        eventos = []
        ev = Events()
        ev.request.add_listener(lambda **kw: eventos.append(kw))
        user = SimpleNamespace(
            client=ClienteComprobantes(srv),
            ctx=ContextoComprobantes(fila=fila_c(modulo, **cambios).con_clave("x")),
            settings=settings,
            environment=SimpleNamespace(events=ev),
            rt=SimpleNamespace(ciclos=RegistroCiclos(tmp_path / "rep" / "ciclos.csv")),
        )
        if preparar:
            req = {"IMPO": maestros.REQ_IMPORTACION, "MODIF": maestros.REQ_MODIFICACION}.get(
                modulo, maestros.REQ_COMPROBANTE
            )
            maestros.preparar_maestros(user, req)
            eventos.clear()
            user.client.respuestas.clear()
        return user, srv, eventos

    return _armar


def _flujo(eventos):
    return {e["name"]: e["exception"] for e in eventos if e["request_type"] == "FLUJO"}


def _validaciones(eventos):
    return {e["name"]: str(e["exception"]) for e in eventos if e["request_type"] == "VALIDACION"}


# ───────────── filas y datos ─────────────


def test_fila_de_comprobantes_un_solo_mes_y_tenancy():
    assert fila_c().etiqueta == "[admin@GDCpruebasQA7 · E6 · 202601 · IMPO]"
    with pytest.raises(ValidationError, match="único mes"):
        fila_c(periodo="202601-202603")
    with pytest.raises(ValidationError, match="tenancy"):
        fila_c(tenancy=None)
    assert fila_c("MODIF", login="gdc", tenancy=None).login == "gdc"


def test_empresa_unica_por_importacion():
    a, b = fila_c(id="A"), fila_c(id="B", usuario="otro")
    assert v.validar_empresa_unica_importacion([a, b])
    assert not v.validar_empresa_unica_importacion([a, fila_c(id="C", usuario="otro", empresa=7)])
    assert not v.validar_empresa_unica_importacion([fila_c("MODIF", id="M1"), fila_c("MODIF", id="M2", usuario="x")])


def test_preparar_datos_filtra_por_escenario_y_valida_por_modulo(proyecto, escribir_csv):
    from holistor_stress.config import cargar_settings

    ruta = escribir_csv(
        "F1,true,866,GDC1,,GDC,3001,202601-202606,COMPRAS,true,",
    )
    texto = ruta.read_text(encoding="utf-8").splitlines()
    texto[0] += ",login,tenancy"
    texto[1] += ",,"
    texto += [
        "I1,true,867,admin,,IMPO,6,202601,,,,plataforma,QA7",
        "M1,true,867,admin,,MODIF,6,202601,,,,plataforma,QA7",
    ]
    ruta.write_text("\n".join(texto) + "\n", encoding="utf-8")
    (proyecto / "environments" / "qa.yaml").write_text(
        (proyecto / "environments" / "qa.yaml").read_text(encoding="utf-8")
        + "plataforma:\n  host_url: https://p.test\n  portal_url: https://p.test\n  front_url: https://f.test\n",
        encoding="utf-8",
    )
    settings = cargar_settings("qa", raiz=proyecto, environ={})
    todo = preparar_datos(settings, environ={"HOLISTOR_QA_CLAVE": "x"})  # admin en IMPO y MODIF: válido
    assert len(todo.filas) == 3
    impo = preparar_datos(settings, environ={"HOLISTOR_QA_CLAVE": "x"}, modulos=["IMPO"])
    assert [f.id for f in impo.filas] == ["I1"] and impo.excluidas_por_escenario == 2


def test_login_plataforma_requiere_seccion():
    assert v.validar_login_plataforma([fila_c()], hay_plataforma=False)
    assert not v.validar_login_plataforma([fila_c()], hay_plataforma=True)


# ───────────── piezas puras ─────────────


def test_csv_de_importacion_con_encabezado_oficial():
    enc = ["Fecha de Emisión", "Importe Total", "Importe Exento"]
    contenido = generar_csv(enc, ";", [{"Fecha de Emisión": "2026-01-01", "Importe Total": monto(1234.5)}])
    lineas = contenido.decode("iso-8859-1").split("\r\n")
    assert lineas[0] == '"Fecha de Emisión";"Importe Total";"Importe Exento"'
    assert lineas[1] == '"2026-01-01";"1234,50";"0,00"'
    with pytest.raises(ValueError, match="columnas"):
        generar_csv(enc, ";", [{"No existe": "1"}])
    cuerpo = multipart("B", {"empCodigo": 6}, "a.csv", b"x;y")
    assert cuerpo.startswith(b'--B\r\nContent-Disposition: form-data; name="empCodigo"\r\n\r\n6\r\n')
    assert cuerpo.endswith(b"x;y\r\n--B--\r\n")


@pytest.mark.parametrize(
    ("body", "esperado"),
    [
        ({"data": {"ccpraId": 7}}, 7),
        ({"result": {"CCPraId": "8"}}, 8),
        ({"data": {"result": {"id": 9}}}, 9),
        ({"data": {"saved": False, "ccpraId": 0}}, None),
        ({"data": True}, None),
        ({}, None),
    ],
)
def test_extraer_id_comprobante(body, esperado):
    assert extraer_id_comprobante(body) == esperado


def test_tabla_de_pasos_del_flujo_completo():
    todos = pasos.ANTES + pasos.DESPUES_GRILLA + pasos.FINAL
    nros = [p.nro for p in todos]
    assert nros == [n for n in range(1, 114) if n not in (6, 103, 108, 109)]
    valores = {k: 1 for k in ("emp", "periodo_id", "periodo_cod", "prov_id", "prov_tipo_doc", "prov_nro_doc",
                              "mov1", "mov2", "fecha", "tenant_id", "user_id", "token")}  # fmt: skip
    valores.update(plataforma="https://p", portal="https://po", front="https://f", back="https://b")
    for p in todos:
        url = p.url.format(**valores)
        assert url.startswith("https://"), p
        assert not [c for _, c, _, _ in string.Formatter().parse(url) if c], p
        p.nombre.format(**valores)
        if p.cuerpo:
            assert isinstance(p.cuerpo(valores), dict)


# ───────────── login y maestros ─────────────


def test_login_plataforma_y_maestros(armar):
    user, srv, _ = armar(preparar=False)
    maestros.preparar_maestros(user, maestros.REQ_IMPORTACION)
    m = user.ctx.maestros
    assert user.ctx.abp_tenant_id == 867 and user.ctx.user_id == "5" and user.ctx.token.startswith("tok-867")
    assert (m.emp_codigo, m.periodo_fiscal_id, m.periodo_fiscal_cod) == (6, 151, "202601")
    assert (m.proveedor_id, m.proveedor_nro_doc, m.proveedor_tipo_doc_abrev) == (24474, 30715954318, "CUIT")
    assert m.mov_tipo_id_venta_neta is None  # la importación no los pide
    assert user.ctx.listo
    # el segundo usuario del mismo tenant/empresa/período usa la cache: sin requests de maestros
    otro, _, _ = armar(preparar=False, servidor=srv)
    antes = len(srv.llamadas)
    maestros.preparar_maestros(otro, maestros.REQ_IMPORTACION)
    assert [r for _, r in srv.llamadas[antes:]] == ["/api/services/app/Account/IsTenantAvailable",
                                                     "/api/TokenAuth/Authenticate"]  # fmt: skip


def test_credenciales_invalidas_es_falla_de_datos(armar):
    user, _, _ = armar(preparar=False, servidor=ServidorComprobantes(clave_valida="otra"))
    with pytest.raises(FallaDatos, match="revisar usuario, clave y tenancy"):
        maestros.preparar_maestros(user, maestros.REQ_IMPORTACION)


def test_empresa_inexistente_es_falla_de_datos(armar):
    user, _, _ = armar(preparar=False, servidor=ServidorComprobantes(empresas=(99,)))
    with pytest.raises(FallaDatos, match="no existe la empresa 6"):
        maestros.preparar_maestros(user, maestros.REQ_IMPORTACION)


def test_relogin_ante_401_y_sesion_invalidada(armar):
    user, srv, _ = armar("MODIF")
    from holistor_stress.api.comprobantes import grilla_compras

    srv.invalidar_sesion(867, "admin")  # alguien más inició sesión: el re-login recupera
    _, total = con_sesion(user, grilla_compras, user, "x", 6, "202601")
    assert total == 3
    flujo = user.settings.flujo.model_copy(update={"relogin_401_max": 0})
    user.settings = user.settings.model_copy(update={"flujo": flujo})
    srv.invalidar_sesion(867, "admin")
    with pytest.raises(SesionInvalidadaError):
        con_sesion(user, grilla_compras, user, "x", 6, "202601")


# ───────────── escenarios ─────────────


def test_importacion_ok(armar, tmp_path):
    user, srv, eventos = armar()
    r = Importacion(user).ejecutar()
    assert r.ok, r.error
    assert _flujo(eventos) == {"IMPO 00 Importacion completa (punta a punta)": None}
    assert r.detalle["comprobantes_antes"] == 3 and r.detalle["comprobantes_nuevos"] == 5
    assert r.detalle["archivo"] == "comprobantes_periodo_202601_compras.csv"
    nombres = user.client.nombres()
    for n in ("IMPO 01 Origen de importacion", "IMPO 04 Subir archivo", "IMPO 09 Lineas del archivo",
              "IMPO 13 Lanzar importacion", "IMPO 14 Seguimiento del job", "IMPO 15 Comprobantes despues"):
        assert n in nombres, n  # fmt: skip
    assert not user.client.fallas()
    assert user.client.cookies["auth_token"] == user.ctx.token
    with (tmp_path / "rep" / "ciclos.csv").open(encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    assert filas[0]["escenario"] == "IMPO" and filas[0]["resultado"] == "OK"
    # segundo ciclo: numeración correlativa, origen desde la memoria del usuario
    imp = Importacion(user)
    imp.ejecutar()
    primero = imp.proximo_numero
    imp.ejecutar()
    assert imp.proximo_numero == primero + 5


def test_importacion_con_lineas_rechazadas_sigue_con_las_validas(armar):
    user, _, eventos = armar(servidor=ServidorComprobantes(lineas_con_error=2))
    r = Importacion(user).ejecutar()
    assert r.ok and r.detalle["comprobantes_nuevos"] == 3
    assert "CUIT inválido (x2)" in _validaciones(eventos)["IMPO 09 Lineas rechazadas por el backend"]


def test_importacion_job_con_errores_es_falla(armar):
    user, _, eventos = armar(servidor=ServidorComprobantes(job_status="FAILED"))
    r = Importacion(user).ejecutar()
    assert not r.ok and "IMPO 14 Seguimiento del job" in r.error
    assert "IMPO 14 Job con errores" in _validaciones(eventos)
    assert "FAILED" in str(_flujo(eventos)["IMPO 00 Importacion completa (punta a punta)"])


def test_importacion_falla_http_dice_el_paso(armar):
    srv = ServidorComprobantes(fallar={"/api/services/app/GdcImpoArchivo/SelectFile": 500})
    user, _, eventos = armar(servidor=srv)
    r = Importacion(user).ejecutar()
    assert not r.ok and r.error.startswith("IMPO 04 Subir archivo: HTTP 500")


def test_importacion_sin_configuracion_es_falla_de_datos(armar):
    user, _, _ = armar(settings_extra={"importacion": None})
    with pytest.raises(FallaDatos, match="importacion"):
        Importacion(user)


def test_modificacion_masiva_ok(armar):
    user, srv, eventos = armar("MODIF")
    r = ModificacionMasiva(user).ejecutar()
    assert r.ok, r.error
    assert r.detalle["cond_fiscal"] == "1 -> 4" and r.detalle["provincia"] == "1 -> 18"
    assert r.detalle["verificados"] == "3/3 con los valores nuevos"
    assert all(c["condFiscal"] == 4 and c["provin"] == 18 for c in srv.cpbtes[(6, "2026-01")])
    # siguiente ciclo: el valor actual ya es 4, se usa el próximo distinto
    r2 = ModificacionMasiva(user).ejecutar()
    assert r2.detalle["cond_fiscal"] == "4 -> 1"


def test_modificacion_sin_comprobantes_es_falla(armar):
    user, _, _ = armar("MODIF", servidor=ServidorComprobantes(comprobantes_iniciales=0))
    r = ModificacionMasiva(user).ejecutar()
    assert not r.ok and "no tiene comprobantes de compra" in r.error


def test_modificacion_codigo_inexistente(armar):
    user, _, _ = armar("MODIF", settings_extra={"modificacion": {"cond_fiscal": [99]}})
    r = ModificacionMasiva(user).ejecutar()
    assert not r.ok and "MODIF 04 Condiciones IVA: los códigos [99] no existen" in r.error


def test_comprobante_lite_ok(armar):
    user, srv, eventos = armar("CPBTE")
    r = ComprobanteLite(user).ejecutar()
    assert r.ok, r.error
    nombres = user.client.nombres()
    assert nombres[:4] == ["/LITE/Lookups/GetAlicuotasVigentes", "/LITE/Lookups/GdcClienteProveedor_Buscar",
                           "/LITE/Lookups/GetClasificacionARCA", "/LITE/Lookups/getMovimientoTipoConsultaLookup_GRC"]
    assert nombres[4:] == ["/LITE/ComprobantesCompra/CREAR_(CORE)", "/LITE/ComprobantesCompra/GetById_DETALLE_1",
                           "/LITE/ComprobantesCompra/GetById_DETALLE_2"]  # fmt: skip
    assert r.detalle["comprobante_id"] > 0


def test_comprobante_duplicado_es_falla(armar):
    user, _, _ = armar("CPBTE", servidor=ServidorComprobantes(crear_sin_id=True))
    r = ComprobanteLite(user).ejecutar()
    assert not r.ok and "DUPLICATE_VOUCHER" in r.error
    assert user.client.nombres()[-1] == "/LITE/ComprobantesCompra/CREAR_(CORE)"  # no pide el detalle


def test_comprobante_completo_113_pasos(armar):
    user, srv, _ = armar("CPBTE")
    r = ComprobanteCompleto(user).ejecutar()
    assert r.ok, r.error
    assert len(user.client.respuestas) == 113 - 1  # 113 pasos, sin el 6 (no existe en la grabación)
    cid = r.detalle["comprobante_id"]
    assert f"/api/service/ComprobantesCompra/{cid}" in user.client.nombres()
    assert not user.client.fallas()
    # los pasos de la plataforma van al host de la plataforma con el userId del login
    assert ("GET", "/api/services/app/AtencionRemota/GetRemoteAssistanceOrder") in srv.llamadas


def test_comprobante_completo_requiere_login_plataforma(armar):
    user, _, _ = armar("CPBTE", login="gdc", tenancy=None, preparar=False)
    with pytest.raises(FallaDatos, match="login=plataforma"):
        ComprobanteCompleto(user)


def test_cuerpo_comprobante_variantes():
    from holistor_stress.core.contexto_comprobantes import Maestros

    m = Maestros(emp_codigo=6, periodo_fiscal_id=151, proveedor_id=1, mov_tipo_id_venta_neta=10,
                 mov_tipo_id_iva_cinco=11)  # fmt: skip
    lite = cuerpo_comprobante(m, "lite", "admin@QA7")
    completo = cuerpo_comprobante(m, "completo")
    assert lite["cabecera"]["CCpraConcepto"].startswith("Stress Locust LITE ")
    assert "user=admin@QA7" in lite["cabecera"]["CCpraConcepto"]
    assert 1 <= completo["cabecera"]["CCpraPtoVenta"] <= 50
    assert set(lite["cabecera"]) == set(completo["cabecera"])
    assert [d["CCpraDetMovId"] for d in lite["detalles"]] == [10, 11]


def test_modificacion_ultima_pagina_incompleta(armar):
    """Regresión: con la última página incompleta, la verificación debe releer la misma ventana."""
    srv = ServidorComprobantes(comprobantes_iniciales=7)
    user, _, _ = armar("MODIF", servidor=srv, settings_extra={"modificacion": {"lote_n": 5}})
    import holistor_stress.flows.modificacion as mod

    original = mod.random.randint
    mod.random.randint = lambda a, b: b  # siempre la última página (2 de 2, con 2 comprobantes)
    try:
        r = ModificacionMasiva(user).ejecutar()
    finally:
        mod.random.randint = original
    assert r.ok, r.error
    assert r.detalle["verificados"] == "2/2 con los valores nuevos"


def test_cada_usuario_tiene_solo_su_tarea():
    """Regresión: Locust suma las tareas de la clase base; el sondeo no debe heredar la tarea de ciclo."""
    from holistor_stress.tasks.comprobantes_tasks import CicloComprobantesTask
    from holistor_stress.users import comprobantes_users as cu

    assert cu.SondeoImportacionUser.tasks == [cu.SondearEstadoTask]
    for cls in (cu.ImportacionComprasUser, cu.ModificacionMasivaUser, cu.ComprobanteLiteUser,
                cu.ComprobanteCompletoUser):  # fmt: skip
        assert cls.tasks == [CicloComprobantesTask], cls
