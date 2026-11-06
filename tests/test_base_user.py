"""Ciclo de vida de HolistorUser dentro de un Environment real de Locust (cliente simulado)."""

import pytest
from locust.env import Environment
from locust.exception import StopUser

from holistor_stress.config.settings import Settings
from holistor_stress.core.pool import PoolExclusivo
from holistor_stress.core.run_info import nueva_corrida
from holistor_stress.core.runtime import HolistorRuntime
from holistor_stress.data.preparacion import DatosPreparados
from holistor_stress.tasks.contexto_tasks import ReabrirPantallaTask
from holistor_stress.users.smoke_users import SmokeContextoUser
from servidor_simulado import GDC, ClienteSimulado, ServidorSimulado
from test_validaciones import fila

HOST = "https://qa.test"


@pytest.fixture
def armar(tmp_path):
    def _armar(*filas, servidor=None, host=HOST, **settings_extra):
        s = Settings.model_validate(
            {"nombre": "qa", "base_url": HOST, "datos": {"users_csv": "x.csv"}, "raiz": tmp_path, **settings_extra}
        )
        filas = filas or (fila(1).con_clave("x"),)
        rt = HolistorRuntime(
            settings=s,
            datos=DatosPreparados(filas=list(filas)),
            pool=PoolExclusivo(filas),
            run=nueva_corrida("qa", HOST),
        )
        env = Environment(user_classes=[SmokeContextoUser], host=host)
        env.holistor = rt
        fallas = []
        env.events.request.add_listener(
            lambda **kw: kw["exception"] and fallas.append((kw["name"], str(kw["exception"])))
        )
        srv = servidor or ServidorSimulado()

        def nuevo_usuario():
            SmokeContextoUser.host = host
            u = SmokeContextoUser(env)
            u.client = ClienteSimulado(srv)
            return u

        return nuevo_usuario, rt, srv, fallas

    return _armar


def test_on_start_toma_fila_y_prepara(armar):
    nuevo, rt, _, fallas = armar()
    u = nuevo()
    u.on_start()
    assert u.ctx.listo and rt.pool.en_uso == 1 and not u.detenido and fallas == []
    u.on_stop()
    assert rt.pool.en_uso == 0 and u.ctx.token is None


def test_falla_de_datos_devuelve_la_fila_y_detiene(armar):
    nuevo, rt, _, fallas = armar(fila(1, periodo="202001").con_clave("x"))
    u = nuevo()
    u.on_start()
    assert u.detenido and rt.pool.en_uso == 0
    esperado = (
        "[GDC1 · E3064 · 202001 · COMPRAS] la empresa 3064 no tiene ejercicio que contiene 202001 "
        "· ejercicios: 5 (2026-01-01 a 2026-12-31), 6 (2027-01-01 a 2027-12-31)"
    )
    # La falla queda en el request que la detectó y en la métrica del flujo.
    assert u.client.fallas() == [esperado]
    assert fallas == [("[Flujo] preparar contexto", esperado)]
    with pytest.raises(StopUser):
        ReabrirPantallaTask(u).on_start()
    u.on_stop()  # Locust llama on_stop después del StopUser: no debe devolver la fila dos veces
    assert rt.pool.disponibles == 1


def test_falla_transitoria_reintenta_y_luego_detiene(armar):
    srv = ServidorSimulado(fallar={f"{GDC}/acceso": 503})
    nuevo, rt, _, _ = armar(servidor=srv, flujo={"setup_reintentos_max": 2})
    u = nuevo()
    u.on_start()
    assert not u.detenido and not u.ctx.listo and rt.pool.en_uso == 1
    assert u.asegurar_contexto() is True  # el 503 era de una sola vez
    srv.fallar = {f"{GDC}/acceso": 503}
    u.preparar()
    srv.fallar = {f"{GDC}/acceso": 503}
    u.preparar()
    assert u.detenido and rt.pool.en_uso == 0


def test_sin_fila_libre(armar):
    nuevo, rt, _, fallas = armar()
    a, b = nuevo(), nuevo()
    a.on_start()
    b.on_start()
    assert b.detenido and b.ctx is None and rt.pool.en_uso == 1
    assert fallas[0][0] == "[Setup] sin fila libre"
    b.on_stop()


def test_guardia_si_cambian_el_host_desde_la_ui(armar):
    nuevo, rt, srv, fallas = armar(host="https://prod.test", urls_produccion=["https://prod.test"])
    u = nuevo()
    u.on_start()
    assert u.detenido and rt.pool.en_uso == 0 and srv.llamadas == []
    assert fallas[0][0] == "[Setup] guardia de producción"


def test_smoke_reabre_la_pantalla_sin_repetir_precheck(armar):
    nuevo, _, srv, fallas = armar()
    u = nuevo()
    u.on_start()
    tarea = ReabrirPantallaTask(u)
    tarea.on_start()
    tarea.reabrir_pantalla()  # primera iteración: el on_start ya preparó, solo espera
    antes = len(srv.llamadas)
    tarea.reabrir_pantalla()
    nuevas = [r for _, r in srv.llamadas[antes:]]
    assert f"{GDC}/acceso" in nuevas and f"{GDC}/precheck-estructura" not in nuevas
    assert "/api/services/app/Account/Authenticate" not in nuevas  # mismo token
    assert fallas == []
