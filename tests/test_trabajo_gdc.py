"""Trabajo GDC de punta a punta contra el servidor simulado (generar → cola → resultado → verificar)."""

import csv
from types import SimpleNamespace

import pytest
from locust.event import Events

from holistor_stress.config.settings import Settings
from holistor_stress.core.context import ContextoAsiento, Envio
from holistor_stress.core.errores import FallaTrabajo
from holistor_stress.flows import verificacion as v
from holistor_stress.flows.contexto import preparar_contexto
from holistor_stress.flows.seguimiento import esperar_finalizacion, normalizar_estado
from holistor_stress.flows.trabajo_gdc import ejecutar_trabajo_gdc
from holistor_stress.reporting.trabajos import RegistroTrabajos
from servidor_simulado import GDC, ClienteSimulado, ServidorSimulado
from test_validaciones import fila


@pytest.fixture
def armar(tmp_path):
    def _armar(servidor=None, flujo=None, **cambios):
        flujo = {"polling": {"intervalo_s": 0.001, "timeout_s": 5}, **(flujo or {})}
        settings = Settings.model_validate(
            {
                "nombre": "qa",
                "base_url": "https://qa.test",
                "datos": {"users_csv": "x"},
                "flujo": flujo,
                "raiz": tmp_path,
            }
        )
        srv = servidor or ServidorSimulado()
        eventos = []
        ev = Events()
        ev.request.add_listener(lambda **kw: eventos.append(kw))
        user = SimpleNamespace(
            client=ClienteSimulado(srv),
            ctx=ContextoAsiento(fila=fila(1, **{"periodo": "202601-202603", **cambios}).con_clave("x")),
            settings=settings,
            environment=SimpleNamespace(events=ev),
            rt=SimpleNamespace(trabajos=RegistroTrabajos(tmp_path / "rep" / "trabajos.csv")),
        )
        preparar_contexto(user)
        eventos.clear()
        return user, srv, eventos

    return _armar


def _e2e(eventos):
    return {e["name"]: e["exception"] for e in eventos if e["request_type"] == "E2E"}


def test_trabajo_ok_registra_metricas_y_csv(armar):
    user, srv, eventos = armar()
    r = ejecutar_trabajo_gdc(user)
    assert r.ok and r.resultado == "OK", r.errores
    assert (r.asientos_total, r.asientos_ok, r.estado_final, r.consultas_progreso) == (3, 3, "Finalizado", 3)
    assert r.s_en_cola is not None and r.s_proceso is not None and r.s_total >= r.s_en_cola
    assert r.s_generar is not None and r.s_trabajo >= r.s_generar
    assert r.control == "estado=Finalizado, total=3, aceptados=3, pendientes=0, rechazados=0"
    assert _e2e(eventos) == {
        "[E2E] GDC encolado→Finalizado": None,
        "[E2E] GDC tiempo En Cola": None,
        "[E2E] GDC tiempo de proceso": None,
        "[E2E] Trabajo completo": None,
    }
    # generar con reemplazar=true y el contexto resuelto
    body = next(c for c in srv.llamadas if c[1].endswith("generar-asiento-comprobantes"))
    assert body
    with user.rt.trabajos.archivo.open(encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    assert len(filas) == 1 and filas[0]["resultado"] == "OK" and filas[0]["request_id"] == r.request_id
    assert filas[0]["fecha_desde"] == "2026-01-01" and filas[0]["meses"] == "3"


def test_asientos_con_error_es_falla_con_pista(armar):
    user, _, eventos = armar(servidor=ServidorSimulado(status_asientos="ERROR"))
    r = ejecutar_trabajo_gdc(user)
    assert r.resultado == "FALLA" and r.estado_final == "Error"
    assert any("3 de 3 asientos no OK" in e and "EmpMod" in e for e in r.errores)
    assert any("tabla de control" in e for e in r.errores)
    falla = str(_e2e(eventos)["[E2E] Trabajo completo"])
    assert falla.startswith("[GDC1 · E3064 · 202601-202603 · COMPRAS] la cola terminó en estado Error")
    assert _e2e(eventos)["[E2E] GDC encolado→Finalizado"] is not None


def test_timeout_de_la_cola(armar):
    srv = ServidorSimulado(consultas_en_cola=10_000)
    user, _, _ = armar(servidor=srv, flujo={"polling": {"intervalo_s": 0.001, "timeout_s": 0.05}})
    r = ejecutar_trabajo_gdc(user)
    assert r.resultado == "FALLA" and "no terminó en 0.05 s" in r.errores[0]


def test_request_id_perdido(armar):
    user, _, _ = armar()
    with pytest.raises(FallaTrabajo, match="requestId perdido"):
        esperar_finalizacion(user, Envio("req-que-no-existe", ({"idAsiento": "x"},), 0.0))


def test_5xx_aislado_en_progreso_se_tolera(armar):
    user, srv, _ = armar()
    original = srv.responder
    fallas = iter([True, False, False, False, False, False])

    def con_un_500(metodo, ruta, *a):
        if ruta.endswith("/progreso") and next(fallas, False):
            return 500, {"error": {"message": "boom"}}
        return original(metodo, ruta, *a)

    srv.responder = con_un_500
    assert ejecutar_trabajo_gdc(user).ok


def test_generar_falla_http_no_corta_al_usuario(armar):
    user, srv, _ = armar()
    srv.fallar = {f"{GDC}/generar-asiento-comprobantes": 500}
    r = ejecutar_trabajo_gdc(user)
    assert r.resultado == "FALLA" and "HTTP 500" in r.errores[0] and r.request_id == ""
    assert r.s_generar is not None  # el tiempo de generar queda aunque falle
    assert ejecutar_trabajo_gdc(user).ok  # el siguiente trabajo funciona


def test_seguimiento_por_jobs_estado(armar):
    user, _, eventos = armar(flujo={"seguimiento": "jobs_estado"})
    r = ejecutar_trabajo_gdc(user)
    assert r.ok and r.s_en_cola is None
    assert "[E2E] GDC tiempo En Cola" not in _e2e(eventos)


def test_ids_repetidos_entre_filas(tmp_path):
    reg = RegistroTrabajos(tmp_path / "t.csv")
    assert reg.ids_repetidos("F1", ["a", "b"]) == []
    assert reg.ids_repetidos("F1", ["a", "b"]) == []  # la misma fila puede regenerarlos
    assert reg.ids_repetidos("F2", ["b", "c"]) == ["b (fila F1)"]


# ── reglas puras ──


def test_normalizar_estado():
    assert [normalizar_estado(e) for e in ("En Cola", "EN PROCESO", " Finalizado ", None)] == [
        "encola",
        "enproceso",
        "finalizado",
        "",
    ]


def test_verificar_destino():
    env = [{"idAsiento": "A"}, {"idAsiento": "B"}]
    dev = [{"idAsiento": "a", "empresa": 1, "ejercicio": 5, "status": "OK"}]
    errores = v.verificar_destino(env, dev, 1, 5)
    assert errores == ["se enviaron 2 asientos y el resultado trae 1", "los IDs devueltos no son los enviados"]
    dev = [{"IdAsiento": "A", "empresa": 2, "ejercicio": 5, "status": "OK"}, {"id": "B", "empresa": 1, "ejercicio": 5}]
    errores = v.verificar_destino(env, dev, 1, 5)
    assert errores[0].startswith("1 de 2 asientos no OK") and "fuera de su destino" in errores[1]


def test_fechas_y_control():
    data = {"lineas": ["Asiento del 31/01/2026", {"texto": "x", "fecha": "2026-02-28T00:00:00"}, {"texto": "sin"}]}
    fechas = v.fechas_de_lineas(data)
    assert fechas == ["2026-01-31", "2026-02-28"]
    assert v.verificar_fechas(fechas, "2026-01-01T00:00:00", "2026-02-28T00:00:00") == []
    assert "fuera de 2026-02-01 a 2026-02-28" in v.verificar_fechas(fechas, "2026-02-01", "2026-02-28")[0]
    assert v.verificar_fechas([], "a", "b") == ["no se pudieron leer las fechas de los asientos (resultado-proceso)"]
    assert v.verificar_control({"aceptados": 3, "pendientes": 0, "rechazados": 0}, 3) == []
    assert v.verificar_control({"aceptados": 2, "pendientes": 1, "rechazados": 0}, 3)
