"""Período de una fila: AAAAMM, AAAAMM-AAAAMM, AAAAMMAAAAMM o TODOS (mismo criterio que la colección)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MES = re.compile(r"^\d{6}$")
_RANGO = re.compile(r"^(\d{6})-(\d{6})$")
_RANGO_PEGADO = re.compile(r"^(\d{6})(\d{6})$")


@dataclass(frozen=True)
class RangoPeriodo:
    """Rango cerrado de meses. `desde`/`hasta` = None significa TODOS (todo el ejercicio)."""

    desde: str | None
    hasta: str | None

    @property
    def todos(self) -> bool:
        return self.desde is None

    def meses(self) -> list[str] | None:
        """Lista de meses AAAAMM del rango; None si es TODOS (depende del ejercicio)."""
        if self.todos:
            return None
        y, m = int(self.desde[:4]), int(self.desde[4:])
        resultado = []
        while f"{y}{m:02d}" <= self.hasta:
            resultado.append(f"{y}{m:02d}")
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return resultado

    @property
    def primer_mes(self) -> str | None:
        return self.desde

    def solapa(self, otro: RangoPeriodo) -> bool:
        if self.todos or otro.todos:
            return True
        return self.desde <= otro.hasta and otro.desde <= self.hasta

    def __str__(self) -> str:
        if self.todos:
            return "TODOS"
        return self.desde if self.desde == self.hasta else f"{self.desde}-{self.hasta}"


def _validar_mes(mes: str, original: str) -> None:
    anio, nro = int(mes[:4]), int(mes[4:])
    if not 1 <= nro <= 12:
        raise ValueError(f"mes inválido '{mes}' en el período '{original}'")
    if not 1900 <= anio <= 2999:
        raise ValueError(f"año inválido '{mes}' en el período '{original}'")


def parsear_periodo(texto: str) -> RangoPeriodo:
    original = str(texto)
    s = original.strip().upper().replace(" ", "")
    if s == "TODOS":
        return RangoPeriodo(None, None)
    if _MES.match(s):
        desde = hasta = s
    elif m := (_RANGO.match(s) or _RANGO_PEGADO.match(s)):
        desde, hasta = m.group(1), m.group(2)
    else:
        raise ValueError(f"período '{original}' con formato inválido: se espera AAAAMM, AAAAMM-AAAAMM o TODOS")
    _validar_mes(desde, original)
    _validar_mes(hasta, original)
    if desde > hasta:
        raise ValueError(f"período '{original}': el mes inicial es posterior al final")
    return RangoPeriodo(desde, hasta)
