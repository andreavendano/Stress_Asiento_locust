"""Resumen de una ejecución, construido SOLO a partir de los archivos de su carpeta.

Así se puede regenerar en cualquier momento (y para corridas viejas) sin volver a correr la prueba.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from holistor_stress.reporting import analisis
from holistor_stress.reporting.sql_verificacion import clave_trabajo, ultimos_por_fila

NOMBRES_ESCENARIO = {
    "smoke_contexto": "Smoke de contexto (no crea asientos)",
    "asiento_gdc": "Generar Asiento GDC de punta a punta",
    "asiento_mixto": "GDC + SYJ concurrentes",
}


def _leer_csv(archivo: Path, delimitador: str = ",") -> list[dict[str, str]]:
    if not archivo.exists():
        return []
    with archivo.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimitador))


def _num(valor: Any) -> float | None:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil por rango más cercano (exacto sobre los datos, sin aproximar como Locust)."""
    datos = sorted(v for v in valores if v is not None)
    if not datos:
        return None
    k = max(0, math.ceil(p / 100 * len(datos)) - 1)
    return datos[k]


def estadistica(valores: list[float]) -> dict[str, float | None]:
    datos = [v for v in valores if v is not None]
    if not datos:
        return {"n": 0, "prom": None, "min": None, "p50": None, "p90": None, "p95": None, "max": None}
    return {
        "n": len(datos),
        "prom": sum(datos) / len(datos),
        "min": min(datos),
        "p50": percentil(datos, 50),
        "p90": percentil(datos, 90),
        "p95": percentil(datos, 95),
        "max": max(datos),
    }


def _requests(carpeta: Path) -> tuple[list[dict], dict | None]:
    filas, total = [], None
    for r in _leer_csv(carpeta / "locust_stats.csv"):
        # Fila corrupta (p. ej. el --csv nativo de Locust en Windows rompe los nombres con "→"): se descarta.
        if (not r.get("Type") and r.get("Name") != "Aggregated") or _num(r.get("Request Count")) is None:
            continue
        item = {
            "tipo": r.get("Type") or "",
            "nombre": r.get("Name") or "",
            "n": int(_num(r.get("Request Count")) or 0),
            "fallas": int(_num(r.get("Failure Count")) or 0),
            "prom_ms": _num(r.get("Average Response Time")),
            "min_ms": _num(r.get("Min Response Time")),
            "max_ms": _num(r.get("Max Response Time")),
            "p50_ms": _num(r.get("50%")),
            "p90_ms": _num(r.get("90%")),
            "p95_ms": _num(r.get("95%")),
            "p99_ms": _num(r.get("99%")),
            "rps": _num(r.get("Requests/s")),
            "kb_prom": (_num(r.get("Average Content Size")) or 0) / 1024,
        }
        if item["nombre"] == "Aggregated":
            total = item
        else:
            filas.append(item)
    return filas, total


def _fallas(carpeta: Path) -> list[dict]:
    return [
        {
            "metodo": r.get("Method", ""),
            "nombre": r.get("Name", ""),
            "error": r.get("Error", ""),
            "n": int(_num(r.get("Occurrences")) or 0),
        }
        for r in _leer_csv(carpeta / "locust_failures.csv")
    ]


def _trabajos(carpeta: Path) -> dict | None:
    filas = _leer_csv(carpeta / "trabajos.csv", ";")
    if not filas:
        return None
    ok = [f for f in filas if f.get("resultado") == "OK"]
    return {
        "total": len(filas),
        "ok": len(ok),
        "falla": len(filas) - len(ok),
        "asientos_total": sum(int(_num(f.get("asientos_total")) or 0) for f in filas),
        "asientos_ok": sum(int(_num(f.get("asientos_ok")) or 0) for f in filas),
        "comprobantes_lote": sum(int(_num(f.get("comprobantes_lote")) or 0) for f in filas),
        "s_total": estadistica([_num(f.get("s_total")) for f in filas]),
        "s_en_cola": estadistica([_num(f.get("s_en_cola")) for f in filas]),
        "s_proceso": estadistica([_num(f.get("s_proceso")) for f in filas]),
        "s_generar": estadistica([_num(f.get("s_generar")) for f in filas]),
        "s_trabajo": estadistica([_num(f.get("s_trabajo")) for f in filas]),
        "errores": [{"fila": f.get("fila"), "errores": f.get("errores")} for f in filas if f.get("resultado") != "OK"],
        "detalle": filas,
    }


def _verificacion(carpeta: Path, trabajos: dict | None) -> dict | None:
    """Une verificacion_resultado.json (consulta a la base) con los trabajos de la corrida."""
    archivo = carpeta / "verificacion_resultado.json"
    if not trabajos or not archivo.exists():
        return None
    v = json.loads(archivo.read_text(encoding="utf-8"))
    filas, huerfanos = [], []
    ultimos, _ = ultimos_por_fila(trabajos["detalle"])

    def buscar(seccion: str, f: dict):
        # clave fila|inicio (desde que puede haber varios trabajos por fila) o solo fila (corridas anteriores)
        datos = v.get(seccion, {})
        return datos.get(clave_trabajo(f), datos.get(str(f.get("fila"))) if clave_trabajo(f) in ultimos else None)

    for f in trabajos["detalle"]:
        if (d := buscar("trabajos", f)) is not None:
            esperados, enviados = _num(f.get("comprobantes_lote")), _num(f.get("asientos_total"))
            coincide = d.get("asientos_ok_control") == enviados and (
                esperados is None or d.get("comprobantes_contabilizados") == esperados
            )
            filas.append({**f, "bd_asientos_ok": d.get("asientos_ok_control"),
                          "bd_comprobantes": d.get("comprobantes_contabilizados"), "bd_coincide": coincide})  # fmt: skip
        if (
            h := v.get("huerfanos", {}).get(
                clave_trabajo(f),
                v.get("huerfanos", {}).get(str(f.get("fila"))) if clave_trabajo(f) in ultimos else None,
            )
        ) is not None:
            asientos = h.get("asientos") or []
            huerfanos.append(
                {
                    **f,
                    "bd_asientos": len(asientos),
                    "bd_asientos_ok": sum(a.get("AsientosStatus") == "OK" for a in asientos),
                    "bd_comprobantes": h.get("comprobantes_contabilizados"),
                    "bd_creados": min((str(a.get("AsientoFechaCreacion"))[:19] for a in asientos), default=""),
                    "bd_ultimo_de_la_fila": clave_trabajo(f) in ultimos,
                }  # fmt: skip
            )
    return {
        "ejecutada": v.get("ejecutada"),
        "base": v.get("base"),
        "verificados": len(filas),
        # trabajos OK que no se consultan: un trabajo posterior de la misma fila reemplazó sus asientos
        "reemplazados": sum(
            1 for f in trabajos["detalle"] if f.get("resultado") == "OK" and clave_trabajo(f) not in ultimos
        ),
        "coinciden": sum(1 for f in filas if f["bd_coincide"]),
        "filas": filas,
        "huerfanos": huerfanos,
        "errores": v.get("errores") or [],
    }


def _historial(carpeta: Path) -> list[dict]:
    return [
        {k: (_num(v) if k != "timestamp" else v) for k, v in r.items()} for r in _leer_csv(carpeta / "historial.csv")
    ]


def _sla(umbrales: dict, requests: list[dict], total: dict | None) -> list[dict]:
    """Compara contra los umbrales del YAML (provisorios hasta acordarlos con producto)."""
    if not umbrales:
        return []
    por_nombre = {r["nombre"]: r for r in requests}
    resultado = []
    http = [r for r in requests if r["tipo"] not in ("E2E", "FLUJO", "SESION", "SETUP")]
    if http and umbrales.get("error_rate_max") is not None:
        n = sum(r["n"] for r in http)
        tasa = (sum(r["fallas"] for r in http) / n) if n else 0.0
        objetivo = umbrales["error_rate_max"]
        resultado.append(
            {
                "criterio": "Tasa de error HTTP",
                "objetivo": f"≤ {objetivo:.1%}",
                "medido": f"{tasa:.2%}",
                "cumple": tasa <= objetivo,
            }  # fmt: skip
        )
    for nombre, maximo in (umbrales.get("p95_ms") or {}).items():
        r = por_nombre.get(nombre)
        if r and r["p95_ms"] is not None:
            resultado.append(
                {
                    "criterio": f"p95 {nombre}",
                    "objetivo": f"≤ {maximo:,.0f} ms",
                    "medido": f"{r['p95_ms']:,.0f} ms",
                    "cumple": r["p95_ms"] <= maximo,
                }  # fmt: skip
            )
    for nombre, maximo in (umbrales.get("e2e_p95_s") or {}).items():
        r = por_nombre.get(nombre)
        if r and r["p95_ms"] is not None:
            resultado.append(
                {
                    "criterio": f"p95 {nombre}",
                    "objetivo": f"≤ {maximo:g} s",
                    "medido": f"{r['p95_ms'] / 1000:.1f} s",
                    "cumple": r["p95_ms"] / 1000 <= maximo,
                }  # fmt: skip
            )
    return resultado


def construir_resumen(carpeta: Path) -> dict:
    info_archivo = carpeta / "run_info.json"
    info = json.loads(info_archivo.read_text(encoding="utf-8")) if info_archivo.exists() else {}
    parametros = info.get("parametros") or {}
    escenario = Path(str(parametros.get("locustfile") or "")).stem or "desconocido"
    requests, total = _requests(carpeta)
    sla = _sla(info.get("thresholds") or {}, requests, total)
    r = {
        "carpeta": carpeta.name,
        "run_id": info.get("run_id", carpeta.name),
        "ambiente": info.get("ambiente", ""),
        "base_url": info.get("base_url", ""),
        "inicio": info.get("inicio", ""),
        "fin": info.get("fin", ""),
        "duracion_s": info.get("duracion_s"),
        "exit_code": info.get("exit_code"),
        "nota": info.get("nota", ""),
        "escenario": escenario,
        "escenario_desc": NOMBRES_ESCENARIO.get(escenario, escenario),
        "parametros": parametros,
        "requests": requests,
        "total": total,
        "fallas": _fallas(carpeta),
        "trabajos": (trabajos := _trabajos(carpeta)),
        "verificacion_bd": _verificacion(carpeta, trabajos),
        "historial": _historial(carpeta),
        "sla": sla,
        "sla_cumple": all(s["cumple"] for s in sla) if sla else None,
    }
    r["hallazgos"] = analisis.hallazgos_automaticos(r)
    r["analisis"] = analisis.leer(carpeta / analisis.ARCHIVO_CORRIDA)
    return r


# ─────────────── Markdown ───────────────

ICONOS = {"ok": "✅", "atencion": "⚠️", "problema": "❌", "info": "ℹ️"}


def _f(v: float | None, dec: int = 1, sufijo: str = "") -> str:
    return "—" if v is None else f"{v:,.{dec}f}{sufijo}"


def resumen_markdown(r: dict) -> str:
    p = r["parametros"]
    t = r["total"] or {}
    lineas = [
        f"# {r['escenario_desc']} · {r['run_id']}",
        "",
        "| Dato | Valor |",
        "|---|---|",
        f"| Ambiente | {r['ambiente']} · {r['base_url']} |",
        f"| Inicio → fin | {r['inicio']} → {r['fin'] or '—'} ({_f(r['duracion_s'], 0, ' s')}) |",
        f"| Usuarios virtuales | {p.get('usuarios', '—')} (spawn {p.get('spawn_rate', '—')}/s) |",
        f"| Trabajos por usuario | {p.get('trabajos_por_usuario') or 'sin límite'} |",
        f"| Filtro de filas | {p.get('filtro_filas') or '—'} |",
        f"| Código de salida | {r['exit_code'] if r['exit_code'] is not None else '—'} |",
    ]
    if r["nota"]:
        lineas.append(f"| Nota | {r['nota']} |")
    if t:
        tasa = t["fallas"] / t["n"] if t["n"] else 0
        lineas += ["", f"**Requests:** {t['n']:,} · **fallas:** {t['fallas']:,} ({tasa:.2%})"]

    if r.get("analisis"):
        lineas += ["", "## Análisis", "", r["analisis"]]
    if r.get("hallazgos"):
        lineas += ["", "## Hallazgos automáticos", ""]
        lineas += [f"- {ICONOS[h['nivel']]} **{h['titulo']}:** {h['texto']}" for h in r["hallazgos"]]

    tr = r["trabajos"]
    if tr:
        lineas += [
            "",
            "## Trabajos de asiento",
            "",
            f"**{tr['ok']} de {tr['total']} trabajos OK** · asientos OK {tr['asientos_ok']} de {tr['asientos_total']}",
            "",
            "| Tiempo (s) | prom | p50 | p90 | p95 | máx |",
            "|---|---|---|---|---|---|",
        ]
        for clave, nombre in (
            ("s_generar", "Generar (POST, antes de encolar)"),
            ("s_total", "Encolado → Finalizado"),
            ("s_en_cola", "En Cola"),
            ("s_proceso", "Proceso"),
            ("s_trabajo", "Trabajo completo"),
        ):
            e = tr.get(clave) or {}
            if not e.get("n"):
                continue  # p. ej. corridas anteriores a la medición de generar
            lineas.append(
                f"| {nombre} | {_f(e['prom'])} | {_f(e['p50'])} | {_f(e['p90'])} | {_f(e['p95'])} | {_f(e['max'])} |"
            )
        lineas += [
            "",
            "### Por trabajo (ordenado por comprobantes del lote)",
            "",
            "| Usuario | Empresa | Tipo | Meses | Comprobantes lote | Precheck | Generar s | Encolado→final s "
            "| En Cola s | Trabajo s | Resultado |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for f in sorted(tr["detalle"], key=lambda f: _num(f.get("comprobantes_lote")) or -1):
            lineas.append(
                f"| {f.get('usuario')} | {f.get('empresa')} | {f.get('tipo_lote')} | {f.get('meses')} | "
                f"{f.get('comprobantes_lote') or '—'} | {f.get('comprobantes_precheck') or '—'} | "
                f"{f.get('s_generar') or '—'} | {f.get('s_total') or '—'} | {f.get('s_en_cola') or '—'} | "
                f"{f.get('s_trabajo') or '—'} | {'✅' if f.get('resultado') == 'OK' else '❌'} {f.get('resultado')} |"
            )
        if tr["errores"]:
            lineas += ["", "**Trabajos con falla:**", ""]
            lineas += [f"- `{e['fila']}`: {e['errores']}" for e in tr["errores"][:20]]

    vb = r.get("verificacion_bd")
    if vb:
        lineas += [
            "",
            "## Verificación en la base",
            "",
            f"Base `{vb['base']}` · consultada {vb['ejecutada']} · **{vb['coinciden']} de {vb['verificados']} trabajos "
            "coinciden** (asientos OK en nuc_AsientosOtrosModulos y comprobantes contabilizados con esos GUID).",
            *(
                [
                    "",
                    f"Se verifica el último trabajo de cada fila: {vb['reemplazados']} trabajos anteriores no se "
                    "consultan porque un trabajo posterior de la misma fila reemplazó sus asientos (reemplazar=true).",
                ]
                if vb.get("reemplazados")
                else []
            ),
            "",
            "| Usuario | Tipo | Asientos OK en control | Comprobantes esperados | Comprobantes contabilizados | Resultado |",
            "|---|---|---|---|---|---|",
        ]
        for f in vb["filas"]:
            lineas.append(
                f"| {f.get('usuario')} | {f.get('tipo_lote')} | {f['bd_asientos_ok']}/{f.get('asientos_total')} | "
                f"{f.get('comprobantes_lote') or '—'} | {f['bd_comprobantes']} | "
                f"{'✅ coincide' if f['bd_coincide'] else '❌ difiere'} |"
            )
        for h in vb["huerfanos"]:
            estado = (
                f"el servidor **sí creó** {h['bd_asientos']} asientos ({h['bd_asientos_ok']} OK, {h['bd_creados']} UTC) "
                f"y contabilizó {h['bd_comprobantes']} comprobantes"
                if h["bd_asientos"]
                else "no hay asientos creados en la base"
            )
            if not h.get("bd_ultimo_de_la_fila", True):
                estado += " (hubo un trabajo posterior de la misma fila: pudo haber reemplazado esos asientos)"
            lineas += [
                "",
                f"**Trabajo con falla sin requestId** · {h.get('usuario')} · {h.get('tipo_lote')}: {estado}.",
            ]
        lineas += [f"- ERROR: {e}" for e in vb["errores"]]

    if r["sla"]:
        lineas += [
            "",
            "## Umbrales (provisorios)",
            "",
            "| Criterio | Objetivo | Medido | Resultado |",
            "|---|---|---|---|",
        ]
        lineas += [
            f"| {s['criterio']} | {s['objetivo']} | {s['medido']} | {'✅ cumple' if s['cumple'] else '❌ no cumple'} |"
            for s in r["sla"]
        ]

    if r["requests"]:
        lineas += [
            "",
            "## Servicios y métricas",
            "",
            "| Tipo | Nombre | # | Fallas | prom ms | p50 | p95 | p99 | máx | KB prom |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for q in r["requests"]:
            lineas.append(
                f"| {q['tipo']} | {q['nombre']} | {q['n']} | {q['fallas']} | {_f(q['prom_ms'], 0)} | "
                f"{_f(q['p50_ms'], 0)} | {_f(q['p95_ms'], 0)} | {_f(q['p99_ms'], 0)} | {_f(q['max_ms'], 0)} | "
                f"{_f(q['kb_prom'], 1)} |"
            )
    if r["fallas"]:
        lineas += ["", "## Fallas", "", "| Nombre | Error | Veces |", "|---|---|---|"]
        lineas += [f"| {f['nombre']} | {f['error'].replace('|', '/')} | {f['n']} |" for f in r["fallas"]]
    lineas += ["", "_Archivos de la corrida: run_info.json, run.log, locust_*.csv, historial.csv, trabajos.csv, "
               "reporte.html._", ""]  # fmt: skip
    return "\n".join(lineas)
