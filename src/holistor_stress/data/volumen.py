"""Volumen de comprobantes por empresa y mes (sale de "Listado de los datos para la carga.xlsx").

Sirve para saber cuántos comprobantes procesa cada trabajo y relacionar el tiempo con el volumen.

    holistor-stress-volumen "Listado de los datos para la carga.xlsx" --salida data/qa/volumen_comprobantes.csv

El .xlsx se lee con la librería estándar (un .xlsx es un zip con XML): no hace falta openpyxl.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

COLUMNAS = ["empresa", "periodo", "compras", "ventas", "certificados"]
# tipoLote de users.csv → columna del listado (el listado no separa certificados emitidos y recibidos).
COLUMNA_POR_TIPO = {
    "COMPRAS": "compras",
    "VENTAS": "ventas",
    "CERTIFICADOS_EMITIDOS": "certificados",
    "CERTIFICADOS_RECIBIDOS": "certificados",
}
_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class Volumen:
    """(empresa, periodo AAAAMM) → {compras, ventas, certificados}."""

    def __init__(self, filas: dict[tuple[int, str], dict[str, int]]):
        self._filas = filas

    def __len__(self) -> int:
        return len(self._filas)

    def comprobantes(self, empresa: int, tipo_lote: str | None, meses: list[str] | tuple[str, ...]) -> int | None:
        """Suma de comprobantes del tipo en esos meses. None si el tipo o algún mes no está en el listado."""
        columna = COLUMNA_POR_TIPO.get((tipo_lote or "").upper())
        if columna is None or not meses:
            return None
        total = 0
        for mes in meses:
            fila = self._filas.get((int(empresa), str(mes)))
            if fila is None:
                return None
            total += fila[columna]
        return total

    @classmethod
    def desde_csv(cls, ruta: Path) -> Volumen:
        filas = {}
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                filas[(int(r["empresa"]), r["periodo"].strip())] = {c: _entero(r.get(c)) for c in COLUMNAS[2:]}
        return cls(filas)


def _entero(v) -> int:
    try:
        return int(float(str(v).strip() or 0))
    except ValueError:
        return 0


def meses_entre(fecha_desde: str, fecha_hasta: str) -> list[str]:
    """'2026-01-01', '2026-06-30' → ['202601', …, '202606']."""
    y, m = int(fecha_desde[:4]), int(fecha_desde[5:7])
    fin = fecha_hasta[:4] + fecha_hasta[5:7]
    meses = []
    while f"{y}{m:02d}" <= fin:
        meses.append(f"{y}{m:02d}")
        m, y = (1, y + 1) if m == 12 else (m + 1, y)
    return meses


# ─────────────── importar el .xlsx ───────────────


def leer_xlsx(ruta: Path) -> list[list[str]]:
    """Filas de la primera hoja como listas de texto (columnas en orden A, B, C…)."""
    with zipfile.ZipFile(ruta) as z:
        compartidas = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                compartidas.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        libro = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        hoja = libro.find("m:sheets", _NS)[0]
        destino = rels[hoja.get(f"{{{_NS['r']}}}id")].lstrip("/")
        destino = destino if destino.startswith("xl/") else f"xl/{destino}"
        filas = []
        for row in ET.fromstring(z.read(destino)).iter(f"{{{_NS['m']}}}row"):
            celdas: dict[int, str] = {}
            for c in row.findall("m:c", _NS):
                col = _indice_columna(re.match(r"[A-Z]+", c.get("r")).group())
                v, en_linea = c.find("m:v", _NS), c.find("m:is", _NS)
                if c.get("t") == "s" and v is not None:
                    celdas[col] = compartidas[int(v.text)]
                elif en_linea is not None:
                    celdas[col] = "".join(t.text or "" for t in en_linea.iter(f"{{{_NS['m']}}}t"))
                else:
                    celdas[col] = v.text if v is not None else ""
            filas.append([celdas.get(i, "") for i in range(max(celdas, default=-1) + 1)])
        return filas


def _indice_columna(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n - 1


def importar_listado(ruta_xlsx: Path) -> list[dict]:
    """Convierte el listado (EmpCodigo, PeriodosCod, Compras, Ventas, Certificados) a filas del CSV."""
    filas = leer_xlsx(ruta_xlsx)
    if not filas:
        raise ValueError(f"{ruta_xlsx} no tiene filas")
    cabecera = [c.strip().lower() for c in filas[0]]
    try:
        i_emp, i_per = cabecera.index("empcodigo"), cabecera.index("periodoscod")
        i_cpr, i_vta, i_cer = cabecera.index("compras"), cabecera.index("ventas"), cabecera.index("certificados")
    except ValueError as e:
        raise ValueError(f"{ruta_xlsx}: faltan columnas (se esperan EmpCodigo, PeriodosCod, Compras, Ventas, "
                         f"Certificados); encontradas: {filas[0]}") from e  # fmt: skip
    salida = []
    for f in filas[1:]:
        f = [c.strip() for c in f] + [""] * 8  # celdas finales vacías no vienen en el XML
        if not f[i_emp] or not f[i_per]:
            continue
        salida.append(
            {
                "empresa": _entero(f[i_emp]),
                "periodo": f[i_per],
                "compras": _entero(f[i_cpr]),
                "ventas": _entero(f[i_vta]),
                "certificados": _entero(f[i_cer]),
            }
        )
    return salida


def main(argv: list[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="holistor-stress-volumen", description=__doc__.splitlines()[0])
    p.add_argument("xlsx", help="Listado de los datos para la carga (.xlsx)")
    p.add_argument("--salida", default="data/qa/volumen_comprobantes.csv")
    a = p.parse_args(argv)
    try:
        filas = importar_listado(Path(a.xlsx))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    salida = Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)
    empresas = sorted({f["empresa"] for f in filas})
    print(f"{len(filas)} filas (empresas {', '.join(map(str, empresas))}) → {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
