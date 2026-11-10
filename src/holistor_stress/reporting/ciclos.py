"""ciclos.csv: una fila por ciclo de los escenarios de comprobantes (importación, modificación masiva, crear).

Separado por `;` para abrirlo en Excel. La columna `detalle` lleva los datos propios del escenario (archivo,
líneas, job, comprobantes antes/después…) en JSON, los mismos que el bloque `[XXX RESUMEN]` del log.
"""

from __future__ import annotations

import csv
import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

COLUMNAS = ["inicio", "escenario", "fila", "tenant", "usuario", "empresa", "periodo", "resultado", "segundos",
            "error", "detalle"]  # fmt: skip


@dataclass
class ResultadoCiclo:
    inicio: str
    escenario: str  # prefijo: IMPO, MODIF, CPBTE…
    fila: str
    tenant: int
    usuario: str
    empresa: Any
    periodo: Any
    resultado: str = "OK"
    segundos: float = 0.0
    error: str = ""
    detalle: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.resultado == "OK"

    def como_fila_csv(self) -> dict:
        d = asdict(self)
        d["segundos"] = f"{self.segundos:.1f}"
        d["detalle"] = json.dumps(self.detalle, ensure_ascii=False, default=str)
        return d


class RegistroCiclos:
    """El archivo se crea con el primer ciclo: las corridas de asientos no dejan un ciclos.csv vacío."""

    def __init__(self, archivo: Path):
        self.archivo = archivo
        self._lock = threading.Lock()
        self.total = 0
        self.fallidos = 0

    def registrar(self, r: ResultadoCiclo) -> None:
        with self._lock:
            self.total += 1
            self.fallidos += 0 if r.ok else 1
            nuevo = not self.archivo.exists()
            self.archivo.parent.mkdir(parents=True, exist_ok=True)
            with self.archivo.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLUMNAS, delimiter=";")
                if nuevo:
                    w.writeheader()
                w.writerow(r.como_fila_csv())
