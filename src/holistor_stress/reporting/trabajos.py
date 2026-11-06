"""trabajos.csv: una fila por trabajo de asiento (equivale al resumen 99.1 de la colección).

Además lleva el control entre trabajos: ningún ID de asiento puede aparecer en dos filas distintas.
"""

from __future__ import annotations

import csv
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class ResultadoTrabajo:
    inicio: str
    fila: str
    tenant: int
    usuario: str
    modulo: str
    empresa: int
    ejercicio: int | None = None
    fecha_desde: str = ""
    fecha_hasta: str = ""
    meses: int = 0
    tipo_lote: str = ""
    comprobantes_precheck: int | None = None  # registros del precheck (1er mes o rango, según flujo.precheck)
    comprobantes_lote: int | None = None  # todos los meses del trabajo, según data/<amb>/volumen_comprobantes.csv
    request_id: str = ""
    asientos_total: int = 0
    asientos_ok: int = 0
    estado_final: str = ""
    consultas_progreso: int = 0
    s_generar: float | None = None  # POST generar (armado sincrónico, antes de encolar)
    s_total: float | None = None  # encolado → estado final
    s_en_cola: float | None = None
    s_proceso: float | None = None
    s_trabajo: float | None = None  # generar + seguir + verificar
    control: str = ""
    resultado: str = ""  # OK | FALLA
    errores: list[str] = field(default_factory=list)
    ids_asientos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores

    def como_fila_csv(self) -> dict:
        d = asdict(self)
        for k in ("s_generar", "s_total", "s_en_cola", "s_proceso", "s_trabajo"):
            d[k] = "" if d[k] is None else f"{d[k]:.1f}"
        d["errores"] = " | ".join(self.errores)
        d["ids_asientos"] = " ".join(self.ids_asientos)
        return d


COLUMNAS = [f.name for f in fields(ResultadoTrabajo)]


class RegistroTrabajos:
    def __init__(self, archivo: Path):
        self.archivo = archivo
        self._lock = threading.Lock()
        self._ids: dict[str, str] = {}  # id de asiento → fila que lo generó
        self.total = 0
        self.fallidos = 0

    def ids_repetidos(self, fila: str, ids: list[str]) -> list[str]:
        """IDs que ya devolvió el trabajo de OTRA fila (control de concurrencia de la carpeta 02)."""
        with self._lock:
            repetidos = [f"{i} (fila {self._ids[i]})" for i in ids if self._ids.get(i, fila) != fila]
            for i in ids:
                self._ids.setdefault(i, fila)
            return repetidos

    def registrar(self, r: ResultadoTrabajo) -> None:
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
