"""Genera resumen.json, resumen.md y reporte.html de cada corrida, y reports/index.html con todas.

Se ejecuta solo al terminar cada prueba. Para regenerar todo (por ejemplo, después de cambiar el
formato del informe):

    holistor-stress-informe                 # todas las carpetas de reports/
    holistor-stress-informe reports/<run>   # una sola corrida (y el índice)
    holistor-stress-informe --completar-volumen data/qa/volumen_comprobantes.csv   # agrega comprobantes_lote
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

from holistor_stress.data.volumen import Volumen, meses_entre
from holistor_stress.reporting import analisis
from holistor_stress.reporting.html import indice, reporte_corrida
from holistor_stress.reporting.resumen import construir_resumen, resumen_markdown
from holistor_stress.reporting.sql_verificacion import generar_sql

logger = logging.getLogger("holistor_stress")


def es_corrida(carpeta: Path) -> bool:
    return carpeta.is_dir() and (carpeta / "run_info.json").exists()


def generar_corrida(carpeta: Path) -> dict:
    r = construir_resumen(carpeta)
    serializable = {k: v for k, v in r.items() if k != "historial"}
    (carpeta / "resumen.json").write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "resumen.md").write_text(resumen_markdown(r), encoding="utf-8")
    (carpeta / "reporte.html").write_text(reporte_corrida(r), encoding="utf-8")
    if sql := generar_sql(r):
        (carpeta / "verificacion.sql").write_text(sql, encoding="utf-8")
    return r


def completar_volumen(carpeta: Path, volumen: Volumen) -> int:
    """Agrega o completa comprobantes_lote en el trabajos.csv de una corrida. Devuelve las filas completadas."""
    archivo = carpeta / "trabajos.csv"
    if not archivo.exists():
        return 0
    with archivo.open(encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=";")
        columnas, filas = list(lector.fieldnames or []), list(lector)
    if "comprobantes_lote" not in columnas:
        pos = columnas.index("comprobantes_precheck") + 1 if "comprobantes_precheck" in columnas else len(columnas)
        columnas.insert(pos, "comprobantes_lote")
    completadas = 0
    for f in filas:
        if f.get("comprobantes_lote") or not f.get("fecha_desde") or not f.get("fecha_hasta"):
            continue
        n = volumen.comprobantes(int(f["empresa"]), f.get("tipo_lote"), meses_entre(f["fecha_desde"], f["fecha_hasta"]))
        f["comprobantes_lote"] = "" if n is None else str(n)
        completadas += n is not None
    with archivo.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, delimiter=";")
        w.writeheader()
        w.writerows(filas)
    return completadas


def generar_indice(raiz_reportes: Path) -> Path:
    resumenes = [construir_resumen(c) for c in sorted(raiz_reportes.iterdir()) if es_corrida(c)]
    destino = raiz_reportes / "index.html"
    general = analisis.leer(raiz_reportes / analisis.ARCHIVO_GENERAL)
    destino.write_text(indice(resumenes, general), encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="holistor-stress-informe", description=__doc__.splitlines()[0])
    p.add_argument("carpetas", nargs="*", help="Carpetas de corridas (por defecto, todas las de --reportes)")
    p.add_argument("--reportes", default="reports", help="Carpeta raíz de las corridas (por defecto reports)")
    p.add_argument(
        "--completar-volumen",
        metavar="CSV",
        help="Completa comprobantes_lote en trabajos.csv con este volumen (p. ej. data/qa/volumen_comprobantes.csv)",
    )
    a = p.parse_args(argv)
    volumen = Volumen.desde_csv(Path(a.completar_volumen)) if a.completar_volumen else None

    raiz = Path(a.reportes)
    if not raiz.is_dir():
        print(f"ERROR: no existe la carpeta {raiz}", file=sys.stderr)
        return 1
    carpetas = [Path(c) for c in a.carpetas] or [c for c in sorted(raiz.iterdir()) if es_corrida(c)]
    for c in carpetas:
        if not es_corrida(c):
            print(f"Salteada (sin run_info.json): {c}", file=sys.stderr)
            continue
        if volumen is not None and (n := completar_volumen(c, volumen)):
            print(f"{c.name}: comprobantes_lote completado en {n} trabajos")
        r = generar_corrida(c)
        tr = r["trabajos"]
        extra = f" · trabajos {tr['ok']}/{tr['total']} OK" if tr else ""
        print(f"{c.name}: {r['escenario']}{extra} → {c / 'reporte.html'}")
    print(f"Índice: {generar_indice(raiz)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
