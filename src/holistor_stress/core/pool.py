"""Pool exclusivo de filas: una fila (= un usuario de la aplicación) por usuario virtual.

Por la política de sesión única, si dos usuarios virtuales usaran la misma fila, el segundo login
invalidaría el token del primero. Por eso las filas no se ciclan: se toman y se devuelven.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterable

from holistor_stress.data.fila import FilaCarga


class SinFilasDisponiblesError(Exception):
    pass


class PoolExclusivo:
    def __init__(self, filas: Iterable[FilaCarga]):
        self._todas = list(filas)
        ids = [f.id for f in self._todas]
        if len(ids) != len(set(ids)):
            repetidos = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"ids de fila repetidos en el pool: {', '.join(repetidos)}")
        self._libres: deque[FilaCarga] = deque(self._todas)
        self._en_uso: set[str] = set()
        self._lock = threading.Lock()  # gevent lo parchea; protege también con hilos reales

    @property
    def total(self) -> int:
        return len(self._todas)

    @property
    def disponibles(self) -> int:
        return len(self._libres)

    @property
    def en_uso(self) -> int:
        return len(self._en_uso)

    def tomar(self) -> FilaCarga:
        with self._lock:
            if not self._libres:
                raise SinFilasDisponiblesError(
                    f"las {self.total} filas están en uso: no hay usuario libre para otro usuario virtual "
                    "(sesión única). Agregar filas a users.csv o bajar la cantidad de usuarios."
                )
            fila = self._libres.popleft()
            self._en_uso.add(fila.id)
            return fila

    def devolver(self, fila: FilaCarga) -> None:
        with self._lock:
            if fila.id not in self._en_uso:
                raise ValueError(f"la fila {fila.id} no estaba tomada")
            self._en_uso.remove(fila.id)
            self._libres.append(fila)


def particionar(filas: list[FilaCarga], partes: int) -> list[list[FilaCarga]]:
    """Reparte las filas en `partes` grupos disjuntos (round-robin), uno por worker de Locust."""
    if partes < 1:
        raise ValueError("partes debe ser >= 1")
    grupos: list[list[FilaCarga]] = [[] for _ in range(partes)]
    for i, fila in enumerate(filas):
        grupos[i % partes].append(fila)
    return grupos
