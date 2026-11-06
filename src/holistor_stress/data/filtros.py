"""Filtro de filas por línea de comando: --filtro-filas "modulo=GDC,tipoLote=VENTAS" (condiciones con Y)."""

from __future__ import annotations

from holistor_stress.data.fila import FilaCarga


def _mapa_campos() -> dict[str, str]:
    mapa = {}
    for nombre, info in FilaCarga.model_fields.items():
        if nombre == "clave":
            continue
        mapa[nombre.lower()] = nombre
        if info.alias:
            mapa[info.alias.lower()] = nombre
    return mapa


def parsear_filtro(texto: str | None) -> dict[str, list[str]]:
    """Devuelve {atributo: [valores aceptados]}. Varios valores con '|': tipoLote=COMPRAS|VENTAS."""
    if not texto or not texto.strip():
        return {}
    mapa = _mapa_campos()
    filtro: dict[str, list[str]] = {}
    for parte in texto.split(","):
        if not parte.strip():
            continue
        if "=" not in parte:
            raise ValueError(f"condición inválida '{parte.strip()}': se espera campo=valor")
        campo, valor = (p.strip() for p in parte.split("=", 1))
        atributo = mapa.get(campo.lower())
        if atributo is None:
            raise ValueError(f"campo desconocido '{campo}' en el filtro. Válidos: {', '.join(sorted(mapa))}")
        filtro[atributo] = [v.strip().lower() for v in valor.split("|") if v.strip()]
    return filtro


def aplicar_filtro(filas: list[FilaCarga], filtro: dict[str, list[str]]) -> list[FilaCarga]:
    def coincide(f: FilaCarga) -> bool:
        return all(str(getattr(f, attr)).lower() in valores for attr, valores in filtro.items())

    return [f for f in filas if coincide(f)] if filtro else list(filas)
