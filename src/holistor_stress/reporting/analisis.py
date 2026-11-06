"""Análisis de una corrida: hallazgos automáticos (reglas sobre los datos) + análisis escrito (analisis.md).

- Los hallazgos automáticos se calculan siempre, así toda corrida queda con un análisis mínimo.
- `analisis.md` en la carpeta de la corrida (y `reports/analisis_general.md` para el índice) es texto
  escrito por QA: se muestra tal cual en reporte.html / index.html y en resumen.md. Se puede editar y
  regenerar con `holistor-stress-informe`.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from html import escape
from pathlib import Path

ARCHIVO_CORRIDA = "analisis.md"
ARCHIVO_GENERAL = "analisis_general.md"

# niveles: "ok" (✓), "atencion" (!), "problema" (✕), "info" (·)
OK, ATENCION, PROBLEMA, INFO = "ok", "atencion", "problema", "info"


def leer(archivo: Path) -> str | None:
    return archivo.read_text(encoding="utf-8").strip() or None if archivo.exists() else None


def _n(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 5:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sx * sy) if sx and sy else None


def _p95(vals: list[float]) -> float | None:
    v = sorted(vals)
    return v[max(0, math.ceil(0.95 * len(v)) - 1)] if v else None


def _h(nivel: str, titulo: str, texto: str) -> dict:
    return {"nivel": nivel, "titulo": titulo, "texto": texto}


def hallazgos_automaticos(r: dict) -> list[dict]:
    """Reglas sobre el resumen de la corrida. Orden: lo más importante primero."""
    h: list[dict] = []
    tr, total = r.get("trabajos"), r.get("total") or {}
    requests = {q["nombre"]: q for q in r.get("requests") or []}

    if tr:
        nivel = OK if not tr["falla"] else PROBLEMA
        texto = f"{tr['ok']} de {tr['total']} trabajos OK · {tr['asientos_ok']:,} asientos"
        if tr.get("comprobantes_lote"):
            texto += f" · {tr['comprobantes_lote']:,} comprobantes procesados"
        if tr["falla"]:
            causas: dict[str, int] = {}
            for e in tr["errores"]:
                causa = re.sub(r"[0-9a-fA-F-]{36}", "<id>", str(e["errores"]).split(" | ")[0])[:90]
                causas[causa] = causas.get(causa, 0) + 1
            texto += ". Fallas: " + "; ".join(f"{c} ({n})" for c, n in causas.items())
        h.append(_h(nivel, "Resultado de los trabajos", texto))
    elif total:
        tasa = total["fallas"] / total["n"] if total["n"] else 0
        h.append(
            _h(OK if not total["fallas"] else PROBLEMA, "Resultado",
               f"{total['n']:,} requests · {total['fallas']} fallas ({tasa:.2%}). Escenario sin generación de asientos.")
        )  # fmt: skip

    vb = r.get("verificacion_bd")
    if vb and vb["verificados"]:
        nivel = OK if vb["coinciden"] == vb["verificados"] else PROBLEMA
        texto = (
            f"{vb['coinciden']} de {vb['verificados']} trabajos coinciden en la base: asientos OK en la tabla de control "
            "y comprobantes contabilizados iguales a los esperados"
        )
        if vb.get("reemplazados"):
            texto += f" (se verifica el último de cada fila; {vb['reemplazados']} anteriores fueron reemplazados)"
        h.append(_h(nivel, "Verificación en la base", texto + "."))
        for x in vb["huerfanos"]:
            if x["bd_asientos"]:
                h.append(
                    _h(ATENCION, "Trabajo completado en el servidor sin respuesta al cliente",
                       f"{x.get('usuario')} ({x.get('tipo_lote')}, {_n(x.get('comprobantes_lote')) or 0:,.0f} comprobantes): "
                       f"el cliente falló ({str(x.get('errores'))[:60]}) pero el servidor creó {x['bd_asientos']} asientos "
                       f"y contabilizó {x['bd_comprobantes']:,} comprobantes. Subir el timeout del cliente.")
                )  # fmt: skip

    if tr and tr["s_trabajo"]["n"]:
        partes = {k: tr[k]["prom"] or 0 for k in ("s_generar", "s_en_cola", "s_proceso")}
        nombres = {"s_generar": "generar (POST, antes de encolar)", "s_en_cola": "En Cola", "s_proceso": "proceso"}
        if not tr["s_generar"]["n"] and tr["s_total"]["n"]:
            # Corridas anteriores a la medición de generar: se estima como trabajo completo − encolado→final
            # (incluye además las consultas de verificación, que son de décimas de segundo).
            partes["s_generar"] = max((tr["s_trabajo"]["prom"] or 0) - (tr["s_total"]["prom"] or 0), 0)
            nombres["s_generar"] = "generar y verificación (estimado)"
        suma = sum(partes.values())
        if suma > 0:
            mayor = max(partes, key=partes.get)
            reparto = " · ".join(f"{nombres[k]} {v:.1f} s ({v / suma:.0%})" for k, v in partes.items() if v)
            nivel = ATENCION if partes[mayor] / suma >= 0.5 and mayor != "s_proceso" else INFO
            h.append(_h(nivel, f"Dónde se va el tiempo: {nombres[mayor]}", f"Promedio por trabajo: {reparto}."))

    if tr and len(tr["detalle"]) >= 5:
        filas = tr["detalle"]
        clave = "s_generar" if tr["s_generar"]["n"] else "s_trabajo"
        pares = [(_n(f.get("comprobantes_lote")), _n(f.get(clave))) for f in filas]
        pares = [(x, y) for x, y in pares if x is not None and y is not None]
        rho = _pearson([x for x, _ in pares], [y for _, y in pares]) if pares else None
        if rho is not None:
            fuerza = "fuerte" if abs(rho) >= 0.7 else "moderada" if abs(rho) >= 0.4 else "débil"
            nombre = "generar" if clave == "s_generar" else "trabajo completo"
            h.append(
                _h(ATENCION if abs(rho) >= 0.4 else INFO, "Relación con el volumen",
                   f"Correlación {fuerza} (r = {rho:.2f}) entre los comprobantes del lote y el tiempo de {nombre}.")
            )  # fmt: skip

    if tr and len(tr["detalle"]) >= 20 and (r.get("duracion_s") or 0) >= 300:
        ordenadas = sorted(tr["detalle"], key=lambda f: str(f.get("inicio")))
        tercio = len(ordenadas) // 3
        ini = _p95([v for f in ordenadas[:tercio] if (v := _n(f.get("s_trabajo"))) is not None])
        fin = _p95([v for f in ordenadas[-tercio:] if (v := _n(f.get("s_trabajo"))) is not None])
        if ini and fin:
            cambio = (fin - ini) / ini
            estable = abs(cambio) < 0.2
            h.append(
                _h(OK if estable or cambio < 0 else PROBLEMA, "Estabilidad durante la prueba",
                   f"p95 del trabajo completo: {ini:.1f} s en el primer tercio y {fin:.1f} s en el último ({cambio:+.0%}). "
                   + ("Sin degradación." if estable else "Hay degradación con el uso sostenido." if cambio > 0 else "Mejora al estabilizarse."))
            )  # fmt: skip

    if tr and (r.get("duracion_s") or 0) >= 60 and tr["total"] >= 10:
        minutos = r["duracion_s"] / 60
        texto = f"{tr['total'] / minutos:.1f} trabajos/min · {tr['asientos_ok'] / minutos:.0f} asientos/min"
        if tr.get("comprobantes_lote"):
            texto += f" · {tr['comprobantes_lote'] / minutos:,.0f} comprobantes/min"
        h.append(_h(INFO, "Rendimiento", texto + f" ({r['parametros'].get('usuarios', '?')} usuarios, un tenant)."))

    for s in r.get("sla") or []:
        if not s["cumple"]:
            h.append(_h(PROBLEMA, "Umbral no cumplido", f"{s['criterio']}: {s['medido']} (objetivo {s['objetivo']})."))

    lentos = [(n, q["p95_ms"]) for n, q in requests.items()
              if n in ("[Auth] Authenticate", "[GDC] acceso") and (q["p95_ms"] or 0) > 3000]  # fmt: skip
    if lentos:
        h.append(
            _h(ATENCION, "Login y apertura de la pantalla lentos con concurrencia",
               " · ".join(f"{n} p95 {v / 1000:.1f} s" for n, v in lentos) + ".")
        )  # fmt: skip
    return h


# ─────────────── Markdown mínimo → HTML (para analisis.md) ───────────────


def _en_linea(texto: str) -> str:
    t = escape(texto)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)


def markdown_a_html(md: str) -> str:
    """Subconjunto: ## / ### títulos, listas (- o 1.) con anidamiento por sangría, tablas |, párrafos,
    **negrita**, *cursiva* y `código`. Una línea en blanco no corta una lista (lista "suelta")."""
    html: list[str] = []
    pila: list[tuple[str, int]] = []  # listas abiertas: (ul|ol, sangría); cada una con un <li> abierto
    tabla: list[str] = []
    parrafo: list[str] = []

    def cerrar_listas(hasta: int = -1):
        while pila and pila[-1][1] > hasta:
            html.append(f"</li></{pila.pop()[0]}>")

    def cerrar_bloques():
        nonlocal tabla, parrafo
        if parrafo:
            html.append(f"<p>{_en_linea(' '.join(parrafo))}</p>")
            parrafo = []
        if tabla:
            filas = [f for f in tabla if not re.fullmatch(r"\|?[\s:|-]+\|?", f)]
            celdas = [[c.strip() for c in f.strip().strip("|").split("|")] for f in filas]
            cab = "".join(f"<th>{_en_linea(c)}</th>" for c in celdas[0])
            cuerpo = "".join("<tr>" + "".join(f"<td>{_en_linea(c)}</td>" for c in f) + "</tr>" for f in celdas[1:])
            html.append(f'<table class="md"><tr>{cab}</tr>{cuerpo}</table>')
            tabla = []

    for linea in md.splitlines():
        s = linea.strip()
        sangria = len(linea) - len(linea.lstrip())
        if not s:
            cerrar_bloques()
        elif m := re.match(r"^(#{1,4})\s+(.*)", s):
            cerrar_bloques()
            cerrar_listas()
            nivel = min(len(m[1]) + 1, 4)
            html.append(f"<h{nivel}>{_en_linea(m[2])}</h{nivel}>")
        elif s.startswith("|"):
            if parrafo:
                cerrar_bloques()
            cerrar_listas()
            tabla.append(s)
        elif m := re.match(r"^([-*]|\d+\.)\s+(.*)", s):
            cerrar_bloques()
            tipo = "ol" if m[1][0].isdigit() else "ul"
            cerrar_listas(sangria)  # vuelve al nivel de esta sangría
            if pila and pila[-1][1] == sangria:
                if pila[-1][0] == tipo:
                    html.append("</li>")  # siguiente ítem de la misma lista
                else:
                    html.append(f"</li></{pila.pop()[0]}>")
            if not pila or pila[-1][1] < sangria or pila[-1][0] != tipo:
                html.append(f"<{tipo}>")  # lista nueva (o sublista dentro del <li> abierto)
                pila.append((tipo, sangria))
            html.append(f"<li>{_en_linea(m[2])}")
        else:
            if tabla:
                cerrar_bloques()
            if pila and sangria > pila[-1][1]:  # continuación del ítem (texto con sangría)
                html.append(f" {_en_linea(s)}")
                continue
            cerrar_listas()
            parrafo.append(s)
    cerrar_bloques()
    cerrar_listas()
    return "".join(html)


def resumen_corto(r: dict) -> str:
    """Una línea para el índice: la primera línea con texto del analisis.md o el hallazgo más relevante."""
    if r.get("analisis"):
        for linea in r["analisis"].splitlines():
            s = linea.strip().lstrip("#-*> ").strip()
            if s and not s.lower().startswith(("análisis", "analisis")):
                return re.sub(r"[*`]", "", s)[:220]
    for nivel in (PROBLEMA, ATENCION, OK, INFO):
        for x in r.get("hallazgos") or []:
            if x["nivel"] == nivel:
                return f"{x['titulo']}: {x['texto']}"[:220]
    return ""


def fecha_corta(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return iso or ""
