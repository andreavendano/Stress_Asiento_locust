"""Usuario virtual base: toma una fila exclusiva, inicia sesión una vez y prepara el contexto.

Ciclo de vida:
- `on_start`: guardia del host → fila del pool (R1) → login → contexto (+ precheck una sola vez).
- Falla de datos o sesión invalidada: registra la falla, devuelve la fila y el usuario virtual se
  detiene en su primera tarea (no martilla el servidor con una fila inválida).
- Falla transitoria (5xx, timeout): el contexto queda incompleto y se reintenta en la próxima
  iteración; después de `flujo.setup_reintentos_max` fallas seguidas, se detiene.
- `on_stop`: devuelve la fila, para que otro usuario virtual pueda usarla (stress / spike).

Ojo: si `on_start` lanza una excepción que no es StopUser, Locust NO llama a `on_stop`. Por eso acá
no se deja escapar ninguna: la fila se devuelve siempre desde este módulo.
"""

from __future__ import annotations

import logging
import random

import gevent
from locust import HttpUser
from locust.exception import StopUser

from holistor_stress.core import metrics
from holistor_stress.core.bootstrap import runtime_de
from holistor_stress.core.context import ContextoAsiento
from holistor_stress.core.errores import FallaDatos, FallaPaso, SesionInvalidadaError
from holistor_stress.core.guardia import GuardiaProduccionError, verificar_ambiente
from holistor_stress.core.pool import SinFilasDisponiblesError
from holistor_stress.flows.contexto import preparar_contexto

logger = logging.getLogger("holistor_stress")

N_CONTEXTO = "[Flujo] preparar contexto"
N_SIN_FILA = "[Setup] sin fila libre"
N_GUARDIA = "[Setup] guardia de producción"


class HolistorUser(HttpUser):
    abstract = True
    # Módulos de users.csv que usa este usuario virtual (None = todas las filas). El bootstrap carga en el
    # pool solo las filas de los módulos de las clases del locustfile.
    modulos_fila: tuple[str, ...] | None = None

    def __init__(self, environment):
        super().__init__(environment)
        self.rt = runtime_de(environment)
        self.settings = self.rt.settings
        self.ctx: ContextoAsiento | None = None
        self.detenido = False
        self.trabajos_hechos = 0
        self._fallas_seguidas = 0
        self._fila_devuelta = False
        self._finalizado = False

    def wait_time(self) -> float:
        wt = self.settings.wait_time
        return random.uniform(wt.min_s, wt.max_s)

    # ───────────── ciclo de vida ─────────────

    def on_start(self) -> None:
        if not self._host_permitido():
            return
        try:
            fila = self.rt.pool.tomar()
        except SinFilasDisponiblesError as e:
            metrics.registrar(self.environment, metrics.TIPO_SETUP, N_SIN_FILA, error=str(e))
            self.detener(f"sin fila: {e}")
            return
        self.ctx = self.nuevo_contexto(fila)
        logger.info("%s usuario virtual iniciado (fila %s)", fila.etiqueta, fila.id)
        self.preparar()

    def on_stop(self) -> None:
        self.liberar()

    # ───────────── puntos de extensión (los usan los escenarios de comprobantes) ─────────────

    def nuevo_contexto(self, fila) -> ContextoAsiento:
        return ContextoAsiento(fila=fila)

    def preparar_contexto(self, con_precheck: bool) -> None:
        """Abre la pantalla del escenario. Por defecto, Generar Asientos (empresa, ejercicio, período, origen)."""
        preparar_contexto(self, con_precheck=con_precheck)

    # ───────────── API para las tareas ─────────────

    def preparar(self, con_precheck: bool = True) -> bool:
        """Prepara el contexto y registra "[Flujo] preparar contexto". True si quedó listo.

        El precheck se ejecuta una sola vez por usuario virtual (R4), aunque se pida de nuevo.
        """
        if self.detenido or self.ctx is None:
            return False
        precheck = con_precheck and self.ctx.registros_precheck is None
        with metrics.cronometro() as ms:
            try:
                self.preparar_contexto(precheck)
            except (FallaDatos, SesionInvalidadaError) as e:
                metrics.registrar(self.environment, metrics.TIPO_FLUJO, N_CONTEXTO, ms(), error=e)
                self.detener(str(e))
                return False
            except FallaPaso as e:
                metrics.registrar(self.environment, metrics.TIPO_FLUJO, N_CONTEXTO, ms(), error=e)
                self._fallas_seguidas += 1
                maximo = self.settings.flujo.setup_reintentos_max
                if self._fallas_seguidas >= maximo:
                    self.detener(f"{e} · {self._fallas_seguidas} fallas seguidas al preparar el contexto")
                else:
                    logger.warning("%s (falla %d de %d, se reintenta)", e, self._fallas_seguidas, maximo)
                return False
            metrics.registrar(self.environment, metrics.TIPO_FLUJO, N_CONTEXTO, ms())
        self._fallas_seguidas = 0
        return True

    def verificar_activo(self) -> None:
        """Lanza StopUser si el usuario virtual quedó detenido (lo usan las tareas)."""
        if self.detenido:
            raise StopUser()

    def asegurar_contexto(self) -> bool:
        """True si el contexto está listo (lo prepara si hace falta). StopUser si quedó detenido."""
        self.verificar_activo()
        listo = self.ctx.listo or self.preparar()
        self.verificar_activo()
        return listo

    def detener(self, motivo: str) -> None:
        logger.error("Usuario virtual detenido: %s", motivo)
        self._finalizar()

    def trabajo_terminado(self) -> None:
        """Cuenta un trabajo. Con --trabajos-por-usuario, al completar la cuota el usuario termina (StopUser)."""
        self.trabajos_hechos += 1
        cuota = self.rt.trabajos_por_usuario
        if cuota and self.trabajos_hechos >= cuota:
            logger.info("%s completó sus %d trabajos", self.ctx.etiqueta, cuota)
            self._finalizar()
            raise StopUser()

    def liberar(self) -> None:
        """Devuelve la fila al pool (una sola vez) y descarta el token."""
        if self.ctx is None or self._fila_devuelta:
            return
        self._fila_devuelta = True
        self.ctx.token = None
        self.rt.pool.devolver(self.ctx.fila)

    # ───────────── internos ─────────────

    def _finalizar(self) -> None:
        """Detiene el usuario virtual (una vez). Con cuota de trabajos, si ya terminaron todos, termina la prueba."""
        self.detenido = True
        self.liberar()
        if self._finalizado:
            return
        self._finalizado = True
        self.rt.usuarios_terminados += 1
        runner = getattr(self.environment, "runner", None)
        objetivo = getattr(runner, "target_user_count", None)
        if self.rt.trabajos_por_usuario and runner is not None and objetivo and self.rt.usuarios_terminados >= objetivo:
            logger.info("Todos los usuarios virtuales terminaron: fin de la prueba")
            gevent.spawn_later(1, runner.quit)

    def _host_permitido(self) -> bool:
        """El host se puede cambiar desde la UI de Locust: la guardia se vuelve a aplicar acá."""
        try:
            verificar_ambiente(self.settings, url_efectiva=self.host, permitir_produccion=self.rt.permitir_produccion)
        except GuardiaProduccionError as e:
            metrics.registrar(self.environment, metrics.TIPO_SETUP, N_GUARDIA, error=str(e))
            self.detener(str(e))
            return False
        return True
