"""Salida de cada ejecución en su carpeta (reports/<run_id>_<escenario>_<N>u/).

Archivos que deja una corrida:
- run_info.json          parámetros, umbrales, inicio, fin, duración y código de salida
- run.log                log de la corrida (sin claves)
- locust_stats.csv       tabla de Locust (mismo formato que --csv), incluye las métricas E2E
- locust_failures.csv    fallas agrupadas por mensaje
- locust_exceptions.csv  excepciones no controladas
- locust_report.html     reporte nativo de Locust (si no se pidió otro --html)
- historial.csv          muestra cada N segundos: usuarios, req/s, fallas/s, p50/p95 y trabajos
- trabajos.csv           una fila por trabajo de asiento
- resumen.json / resumen.md / reporte.html   generados por reporting.informe
"""

from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import gevent
from locust import stats as locust_stats

logger = logging.getLogger("holistor_stress")

HISTORIAL_COLUMNAS = [
    "timestamp",
    "segundos",
    "usuarios",
    "rps",
    "fallas_s",
    "p50_ms",
    "p95_ms",
    "trabajos",
    "trabajos_falla",
]
FORMATO_LOG = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def agregar_log_archivo(carpeta: Path) -> logging.Handler:
    """Copia el log de la corrida (Locust + framework) a run.log."""
    handler = logging.FileHandler(carpeta / "run.log", encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(FORMATO_LOG))
    logging.getLogger().addHandler(handler)
    return handler


def escribir_csv_locust(environment, carpeta: Path) -> None:
    """Escribe las tablas de Locust con su formato nativo (--csv no se puede redirigir desde el framework)."""
    escritor = locust_stats.StatsCSV(environment, locust_stats.PERCENTILES_TO_REPORT)
    for nombre, metodo in (
        ("locust_stats.csv", escritor.requests_csv),
        ("locust_failures.csv", escritor.failures_csv),
        ("locust_exceptions.csv", escritor.exceptions_csv),
    ):
        with (carpeta / nombre).open("w", encoding="utf-8", newline="") as f:
            metodo(csv.writer(f))


def completar_run_info(carpeta: Path, exit_code: int | None, inicio_monotonic: float | None) -> None:
    archivo = carpeta / "run_info.json"
    info = json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else {}
    info["fin"] = datetime.now().isoformat(timespec="seconds")
    if inicio_monotonic is not None:
        info["duracion_s"] = round(time.monotonic() - inicio_monotonic, 1)
    info["exit_code"] = exit_code
    archivo.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


class Muestreador:
    """Greenlet que agrega una fila a historial.csv cada `intervalo_s` mientras corre la prueba."""

    def __init__(self, environment, carpeta: Path, intervalo_s: float = 5.0):
        self.environment = environment
        self.archivo = carpeta / "historial.csv"
        self.intervalo_s = intervalo_s
        self._greenlet = None
        self._inicio = None

    def iniciar(self) -> None:
        if self._greenlet is not None:
            return
        self._inicio = time.monotonic()
        with self.archivo.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(HISTORIAL_COLUMNAS)
        self._greenlet = gevent.spawn(self._bucle)

    def detener(self) -> None:
        if self._greenlet is not None:
            self.muestra()
            self._greenlet.kill(block=False)
            self._greenlet = None

    def _bucle(self) -> None:
        while True:
            gevent.sleep(self.intervalo_s)
            try:
                self.muestra()
            except Exception:  # el historial nunca debe tirar la prueba
                logger.exception("No se pudo escribir historial.csv")

    def muestra(self) -> None:
        env = self.environment
        total = env.stats.total
        runner = env.runner
        registro = getattr(getattr(env, "holistor", None), "trabajos", None)

        def pct(p: float) -> int | str:
            v = total.get_current_response_time_percentile(p)
            return int(v) if v else ""

        fila = [
            datetime.now().isoformat(timespec="seconds"),
            round(time.monotonic() - (self._inicio or time.monotonic()), 1),
            runner.user_count if runner is not None else "",
            round(total.current_rps or 0, 2),
            round(total.current_fail_per_sec or 0, 2),
            pct(0.5),
            pct(0.95),
            registro.total if registro else 0,
            registro.fallidos if registro else 0,
        ]
        with self.archivo.open("a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(fila)
