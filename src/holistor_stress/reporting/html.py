"""HTML autocontenido (sin CDN: se abre sin conexión) para cada corrida y para el índice de corridas.

Gráficos en SVG generado acá + un script mínimo para tooltips y crosshair. Paleta: slots 1-2 de la
paleta categórica de referencia (validada) y colores de estado siempre con icono + texto.
"""

from __future__ import annotations

import json
import math
from html import escape

from holistor_stress.reporting import analisis

# ─────────────── estilos y script comunes ───────────────

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--good:#0ca30c;--good-ink:#006300;
--crit:#d03b3b;--warn:#fab219}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--page:#0d0d0d;
--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--good-ink:#0ca30c}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;--good-ink:#0ca30c}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:32px 0 10px}
.sub{color:var(--ink2);margin:0 0 16px}.muted{color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 20px}
.chip{border:1px solid var(--ring);border-radius:999px;padding:2px 10px;color:var(--ink2);background:var(--surface)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.tile .v{font-size:26px;font-weight:600;margin-top:2px}.tile .l{color:var(--ink2);font-size:13px}
.tile .d{color:var(--muted);font-size:12px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px 16px;overflow-x:auto}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:12px}td.n,th.n{text-align:right}
.st{display:inline-flex;align-items:center;gap:4px;font-weight:600;white-space:nowrap}
.st.ok{color:var(--good-ink)}.st.ko{color:var(--crit)}.st.na{color:var(--muted)}
.legend{display:flex;gap:16px;color:var(--ink2);font-size:13px;margin:4px 0 8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
svg{display:block;width:100%;height:auto}svg text{fill:var(--muted);font-size:11px}
svg .lbl{fill:var(--ink2)}svg .falla{fill:var(--crit);font-weight:600}.grid line{stroke:var(--grid);stroke-width:1}.base{stroke:var(--axis)}
.hit{fill:transparent;cursor:default}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);
border-radius:8px;padding:6px 10px;box-shadow:0 4px 16px rgba(0,0,0,.12);font-size:12px;display:none;z-index:10;
max-width:360px}
#tip b{font-size:13px}
details summary{cursor:pointer;color:var(--ink2);margin:8px 0}
a{color:var(--s1)}
.err{color:var(--ink2);font-size:12px;max-width:520px}
.st.warn{color:#b26b00}
:root[data-theme="dark"] .st.warn{color:var(--warn)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .st.warn{color:var(--warn)}}
ul.hallazgos{list-style:none;margin:0;padding:0}
ul.hallazgos li{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid var(--grid)}
ul.hallazgos li:last-child{border-bottom:0}
ul.hallazgos .st{min-width:14px;justify-content:center}
.analisis h2,.analisis h3,.analisis h4{font-size:15px;margin:14px 0 6px}
.analisis > :first-child{margin-top:0}
.analisis p,.analisis li{max-width:900px}
.analisis code{background:var(--page);border:1px solid var(--ring);border-radius:4px;padding:0 4px;font-size:12px}
.analisis table.md{margin:8px 0}
.resumen-corto{color:var(--ink2);font-size:12px;max-width:460px;margin-top:2px}
details > .card{margin-top:4px}
"""

JS = """
const tip=document.getElementById('tip');
function show(e,lines){tip.replaceChildren();lines.forEach((t,i)=>{const el=document.createElement(i?'div':'b');
el.textContent=t;tip.appendChild(el)});tip.style.display='block';
const x=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8),y=Math.min(e.clientY+14,innerHeight-tip.offsetHeight-8);
tip.style.left=x+'px';tip.style.top=y+'px'}
function hide(){tip.style.display='none'}
document.querySelectorAll('[data-tip]').forEach(el=>{const l=el.dataset.tip.split('\\n');
el.addEventListener('pointermove',e=>show(e,l));el.addEventListener('pointerleave',hide)});
document.querySelectorAll('svg[data-pts]').forEach(svg=>{const pts=JSON.parse(svg.dataset.pts);
const cross=svg.querySelector('.cross'),dot=svg.querySelector('.dot'),hit=svg.querySelector('.hit');
hit.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),vb=svg.viewBox.baseVal;
const x=(e.clientX-r.left)*vb.width/r.width;let best=pts[0];for(const p of pts){if(Math.abs(p[0]-x)<Math.abs(best[0]-x))best=p}
cross.setAttribute('x1',best[0]);cross.setAttribute('x2',best[0]);cross.style.display='';
dot.setAttribute('cx',best[0]);dot.setAttribute('cy',best[1]);dot.style.display='';show(e,[best[3],best[2]])});
hit.addEventListener('pointerleave',()=>{cross.style.display='none';dot.style.display='none';hide()})});
"""


def pagina(titulo: str, cuerpo: str) -> str:
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(titulo)}</title><style>{CSS}</style></head><body><main>{cuerpo}</main>"
        f'<div id="tip" role="tooltip"></div><script>{JS}</script></body></html>'
    )


# ─────────────── utilidades ───────────────


def e(texto) -> str:
    return escape("" if texto is None else str(texto))


def fmt(v, dec: int = 1, suf: str = "") -> str:
    return "—" if v is None else f"{v:,.{dec}f}{suf}"


def estado(cumple: bool | None, si: str = "cumple", no: str = "no cumple") -> str:
    if cumple is None:
        return '<span class="st na">– sin datos</span>'
    if cumple:
        return f'<span class="st ok" aria-label="{si}">✓ {e(si)}</span>'
    return f'<span class="st ko" aria-label="{no}">✕ {e(no)}</span>'


def tile(etiqueta: str, valor: str, detalle: str = "") -> str:
    d = f'<div class="d">{detalle}</div>' if detalle else ""
    return f'<div class="tile"><div class="l">{e(etiqueta)}</div><div class="v">{valor}</div>{d}</div>'


def _maximo_lindo(v: float) -> float:
    if v <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


def _escala(v: float, n: int = 4) -> tuple[float, list[float]]:
    """Máximo del eje y marcas con un paso "redondo" (1, 2, 2,5 o 5 × 10^k)."""
    paso = _maximo_lindo((v or 1) / n)
    pasos = max(1, math.ceil((v or 1) / paso - 1e-9))
    return paso * pasos, [paso * i for i in range(pasos + 1)]


def _num_tick(v: float) -> str:
    return f"{v:,.0f}" if v >= 10 or v == 0 else f"{round(v, 2):g}"


def _barra_redondeada(x: float, y: float, w: float, h: float, r: float = 3) -> str:
    """Rectángulo con el extremo derecho redondeado (el extremo de datos); el izquierdo ancla en la base."""
    r = min(r, w / 2, h / 2)
    if w <= 0:
        return ""
    return f"M{x:.1f},{y:.1f}h{w - r:.1f}a{r},{r} 0 0 1 {r},{r}v{h - 2 * r:.1f}a{r},{r} 0 0 1 {-r},{r}h{-(w - r):.1f}z"


# ─────────────── gráficos ───────────────


def barras_apiladas(items: list[dict], series: list[tuple[str, str]], unidad: str = "s") -> str:
    """Barras horizontales apiladas. items: {etiqueta, valores: [..por serie..], tip, marca}."""
    if not items:
        return ""
    ancho, izq, der, alto_fila, arriba = 800, 250, 16, 22, 8
    total_max, marcas = _escala(max(sum(v or 0 for v in it["valores"]) for it in items))
    escala = (ancho - izq - der) / total_max
    alto = arriba + len(items) * alto_fila + 24
    partes = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Tiempo por trabajo">', '<g class="grid">']
    for t in marcas:
        x = izq + t * escala
        partes.append(f'<line x1="{x:.1f}" y1="{arriba}" x2="{x:.1f}" y2="{alto - 20}"/>')
        partes.append(f'<text x="{x:.1f}" y="{alto - 6}" text-anchor="middle">{_num_tick(t)} {unidad}</text>')
    partes.append("</g>")
    for i, it in enumerate(items):
        y = arriba + i * alto_fila + 4
        h = alto_fila - 8
        partes.append(
            f'<text class="lbl" x="{izq - 8}" y="{y + h / 2 + 4:.1f}" text-anchor="end">{e(it["etiqueta"])}</text>'
        )
        x = izq
        valores = [v or 0 for v in it["valores"]]
        ultimo = max((j for j, v in enumerate(valores) if v > 0), default=-1)
        for j, v in enumerate(valores):
            if v <= 0:
                continue
            w = max(v * escala - (0 if j == ultimo else 2), 1)
            color = series[j][1]
            if j == ultimo:
                partes.append(f'<path d="{_barra_redondeada(x, y, w, h)}" fill="{color}"/>')
            else:
                partes.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" fill="{color}"/>')
            x += v * escala
        if it.get("marca"):
            partes.append(f'<text x="{x + 6:.1f}" y="{y + h / 2 + 4:.1f}" class="falla">✕ falla</text>')
        partes.append(
            f'<rect class="hit" x="0" y="{y - 4}" width="{ancho}" height="{alto_fila}" data-tip="{e(it["tip"])}"/>'
        )
    partes.append(f'<line class="base" x1="{izq}" y1="{arriba}" x2="{izq}" y2="{alto - 20}"/></svg>')
    leyenda = "".join(f'<span><i style="background:{c}"></i>{e(n)}</span>' for n, c in series)
    return f'<div class="legend">{leyenda}</div>' + "".join(partes)


def linea(titulo: str, puntos: list[tuple[float, float]], formato_x, unidad: str, dec: int = 0) -> str:
    """Pequeño gráfico de línea (una serie, un eje) con crosshair. puntos: (x en s, y)."""
    puntos = [(x, y) for x, y in puntos if x is not None and y is not None]
    if len(puntos) < 2:
        return ""
    ancho, alto, izq, der, arriba, abajo = 360, 160, 44, 10, 10, 24
    xmax = max(x for x, _ in puntos) or 1
    ymax, marcas = _escala(max(y for _, y in puntos), 3)
    sx = (ancho - izq - der) / xmax
    sy = (alto - arriba - abajo) / ymax
    pts = [(izq + x * sx, alto - abajo - y * sy, f"{y:,.{dec}f} {unidad}".strip(), formato_x(x)) for x, y in puntos]
    camino = " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (px, py, _, _) in enumerate(pts))
    partes = [
        f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="{e(titulo)}" '
        f"data-pts='{e(json.dumps([[round(a, 1), round(b, 1), c, d] for a, b, c, d in pts]))}'>",
        '<g class="grid">',
    ]
    for t in marcas:
        y = alto - abajo - t * sy
        partes.append(f'<line x1="{izq}" y1="{y:.1f}" x2="{ancho - der}" y2="{y:.1f}"/>')
        partes.append(f'<text x="{izq - 6}" y="{y + 4:.1f}" text-anchor="end">{_num_tick(t)}</text>')
    partes.append("</g>")
    for frac in (0, 0.5, 1):
        x = izq + xmax * frac * sx
        partes.append(f'<text x="{x:.1f}" y="{alto - 6}" text-anchor="middle">{e(formato_x(xmax * frac))}</text>')
    partes += [
        f'<path d="{camino}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round"/>',
        f'<line class="cross" x1="0" x2="0" y1="{arriba}" y2="{alto - abajo}" stroke="var(--axis)" style="display:none"/>',
        '<circle class="dot" r="4" fill="var(--s1)" stroke="var(--surface)" stroke-width="2" style="display:none"/>',
        f'<rect class="hit" x="{izq}" y="0" width="{ancho - izq - der}" height="{alto}"/></svg>',
    ]
    return f'<div class="card"><div class="l" style="color:var(--ink2)">{e(titulo)}</div>{"".join(partes)}</div>'


def columnas(titulo: str, items: list[tuple[str, float | None, str]], unidad: str) -> str:
    """Columnas verticales, una serie. items: (etiqueta, valor, tip)."""
    items = [it for it in items if it[1] is not None]
    if not items:
        return ""
    ancho, alto, izq, abajo, arriba = 560, 200, 44, 40, 10
    paso = (ancho - izq - 8) / len(items)
    w = max(min(paso * 0.6, 48), 4)
    ymax, marcas = _escala(max(v for _, v, _ in items), 3)
    sy = (alto - arriba - abajo) / ymax
    partes = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="{e(titulo)}"><g class="grid">']
    for t in marcas:
        y = alto - abajo - t * sy
        partes.append(f'<line x1="{izq}" y1="{y:.1f}" x2="{ancho - 8}" y2="{y:.1f}"/>')
        partes.append(f'<text x="{izq - 6}" y="{y + 4:.1f}" text-anchor="end">{_num_tick(t)}</text>')
    partes.append("</g>")
    for i, (etq, v, tip) in enumerate(items):
        x = izq + i * paso + (paso - w) / 2
        h = max(v * sy, 1)
        y = alto - abajo - h
        r = min(3, w / 2, h)
        d = f"M{x:.1f},{alto - abajo}v{-(h - r):.1f}a{r},{r} 0 0 1 {r},{-r}h{w - 2 * r:.1f}a{r},{r} 0 0 1 {r},{r}v{h - r:.1f}z"
        partes.append(f'<path d="{d}" fill="var(--s1)"/>')
        partes.append(
            f'<text class="lbl" x="{x + w / 2:.1f}" y="{alto - abajo + 14}" text-anchor="middle">{e(etq)}</text>'
        )
        partes.append(f'<rect class="hit" x="{izq + i * paso:.1f}" y="0" width="{paso:.1f}" height="{alto}" '
                      f'data-tip="{e(tip)}"/>')  # fmt: skip
    partes.append(f'<line class="base" x1="{izq}" y1="{alto - abajo}" x2="{ancho - 8}" y2="{alto - abajo}"/></svg>')
    return f'<div class="card"><div class="l" style="color:var(--ink2)">{e(titulo)}</div>{"".join(partes)}</div>'


def dispersion(titulo: str, puntos: list[tuple[float, float, str, bool]], eje_x: str, eje_y: str) -> str:
    """Puntos (x, y, tip, falla): una serie, un eje. Las fallas llevan además una cruz (no solo color)."""
    puntos = [p for p in puntos if p[0] is not None and p[1] is not None]
    if len(puntos) < 2:
        return ""
    ancho, alto, izq, der, arriba, abajo = 560, 230, 48, 28, 10, 38
    xmax, marcas_x = _escala(max(p[0] for p in puntos))
    ymax, marcas_y = _escala(max(p[1] for p in puntos))
    sx, sy = (ancho - izq - der) / xmax, (alto - arriba - abajo) / ymax
    partes = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="{e(titulo)}"><g class="grid">']
    for t in marcas_y:
        y = alto - abajo - t * sy
        partes.append(f'<line x1="{izq}" y1="{y:.1f}" x2="{ancho - der}" y2="{y:.1f}"/>')
        partes.append(f'<text x="{izq - 6}" y="{y + 4:.1f}" text-anchor="end">{_num_tick(t)}</text>')
    for t in marcas_x:
        x = izq + t * sx
        partes.append(f'<text x="{x:.1f}" y="{alto - abajo + 14}" text-anchor="middle">{_num_tick(t)}</text>')
    partes.append("</g>")
    partes.append(f'<text x="{(izq + ancho - der) / 2:.0f}" y="{alto - 4}" text-anchor="middle">{e(eje_x)}</text>')
    partes.append(f'<text x="12" y="{arriba + 4}" class="lbl">{e(eje_y)}</text>')
    partes.append(f'<line class="base" x1="{izq}" y1="{alto - abajo}" x2="{ancho - der}" y2="{alto - abajo}"/>')
    for x, y, tip, falla in sorted(puntos, key=lambda p: p[3]):  # fallas arriba
        cx, cy = izq + x * sx, alto - abajo - y * sy
        color = "var(--crit)" if falla else "var(--s1)"
        partes.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{color}" stroke="var(--surface)" stroke-width="2"/>'
        )
        if falla:
            partes.append(f'<text x="{cx + 8:.1f}" y="{cy + 4:.1f}" class="falla">✕</text>')
        partes.append(f'<circle class="hit" cx="{cx:.1f}" cy="{cy:.1f}" r="12" data-tip="{e(tip)}"/>')
    partes.append("</svg>")
    return f'<div class="card"><div class="l" style="color:var(--ink2)">{e(titulo)}</div>{"".join(partes)}</div>'


def _mmss(s: float) -> str:
    s = int(round(s or 0))
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else f"{s} s"


# ─────────────── reporte de una corrida ───────────────


def reporte_corrida(r: dict) -> str:
    p, t, tr = r["parametros"], r["total"] or {}, r["trabajos"]
    chips = [
        f"Ambiente {r['ambiente']}",
        f"{p.get('usuarios', '?')} usuarios",
        f"spawn {p['spawn_rate']:g}/s" if p.get("spawn_rate") else "",
        (f"{p.get('trabajos_por_usuario') or 'sin límite de'} trabajos por usuario")
        if r["escenario"].startswith("asiento")
        else "",
        f"duración {_mmss(r['duracion_s'])}" if r["duracion_s"] is not None else "",
        f"filtro {p['filtro_filas']}" if p.get("filtro_filas") else "",
        f"exit code {r['exit_code']}" if r["exit_code"] is not None else "",
    ]
    partes = [
        f"<h1>{e(r['escenario_desc'])}</h1>",
        f'<p class="sub">{e(r["run_id"])} · {e(r["inicio"])} → {e(r["fin"] or "—")} · {e(r["base_url"])}</p>',
        '<div class="chips">' + "".join(f'<span class="chip">{e(c)}</span>' for c in chips if c) + "</div>",
    ]
    if r["nota"]:
        partes.append(f'<p class="muted">{e(r["nota"])}</p>')

    tiles = []
    if tr:
        tiles.append(
            tile(
                "Trabajos OK",
                f"{tr['ok']} / {tr['total']}",
                estado(tr["falla"] == 0, "todos OK", f"{tr['falla']} con falla"),
            )
        )
        tiles.append(tile("Asientos OK", f"{tr['asientos_ok']} / {tr['asientos_total']}"))
        tiles.append(tile("p95 encolado → Finalizado", fmt(tr["s_total"]["p95"], 1, " s"),
                          f"p50 {fmt(tr['s_total']['p50'], 1, ' s')} · máx {fmt(tr['s_total']['max'], 1, ' s')}"))  # fmt: skip
        tiles.append(tile("p95 tiempo En Cola", fmt(tr["s_en_cola"]["p95"], 1, " s"),
                          f"máx {fmt(tr['s_en_cola']['max'], 1, ' s')}"))  # fmt: skip
        if tr.get("s_generar", {}).get("n"):
            tiles.append(tile("p95 generar (antes de encolar)", fmt(tr["s_generar"]["p95"], 1, " s"),
                              f"p50 {fmt(tr['s_generar']['p50'], 1, ' s')} · máx {fmt(tr['s_generar']['max'], 1, ' s')}"))  # fmt: skip
    if t:
        tasa = t["fallas"] / t["n"] if t["n"] else 0
        tiles.append(tile("Requests", f"{t['n']:,}", f"{t['fallas']:,} fallas ({tasa:.2%}) · {fmt(t['rps'], 2)} req/s"))
    vb = r.get("verificacion_bd")
    if vb and vb["verificados"]:
        huerf = [h for h in vb["huerfanos"] if h["bd_asientos"]]
        tiles.append(
            tile(
                "Verificación en la base",
                f"{vb['coinciden']} / {vb['verificados']}",
                estado(vb["coinciden"] == vb["verificados"], "coinciden", "con diferencias")
                + (f"<br>{len(huerf)} trabajo(s) con falla igual creados" if huerf else ""),
            )
        )
    if r["sla_cumple"] is not None:
        tiles.append(tile("Umbrales provisorios", estado(r["sla_cumple"], "cumple", "no cumple")))
    if tiles:
        partes.append('<div class="tiles">' + "".join(tiles) + "</div>")
    partes.append(_seccion_analisis(r))

    if tr and tr["detalle"]:
        filas = tr["detalle"][:80]
        items = []
        con_generar = any(_float(f.get("s_generar")) is not None for f in filas)  # corridas viejas no lo tienen
        for f in filas:
            gen = _float(f.get("s_generar"))
            cola, proc = _float(f.get("s_en_cola")), _float(f.get("s_proceso"))
            total = _float(f.get("s_total"))
            if cola is None and proc is None and total is not None:
                proc = total
            suma = sum(v or 0 for v in (gen, cola, proc))
            tip = (
                f"{fmt(suma, 1, ' s')} hasta {f.get('estado_final') or 'sin estado final'}"
                f" · inicio {f.get('inicio', '')[11:19]}\n"
                f"{f.get('usuario')} · E{f.get('empresa')} · {f.get('tipo_lote')} · {f.get('meses')} meses\n"
                f"{_comprobantes(f)}\n"
                + (f"Generar {fmt(gen, 1, ' s')} · " if con_generar else "")
                + f"En Cola {fmt(cola, 1, ' s')} · proceso {fmt(proc, 1, ' s')}\n"
                f"asientos {f.get('asientos_ok')}/{f.get('asientos_total')} · {f.get('resultado')}"
            )
            if f.get("errores"):
                tip += f"\n{f['errores'][:200]}"
            items.append(
                {
                    "etiqueta": f"{f.get('usuario')} · {f.get('tipo_lote', '')[:7]}"
                    + (
                        f" · {int(_float(f['comprobantes_lote'])):,} cpbtes"
                        if _float(f.get("comprobantes_lote"))
                        else f" {f.get('inicio', '')[11:19]}"
                    ),
                    "valores": [gen, cola, proc] if con_generar else [cola, proc],
                    "tip": tip,
                    "marca": f.get("resultado") != "OK",
                }
            )
        series = [("En Cola", "var(--s1)"), ("Proceso", "var(--s2)")]
        if con_generar:
            series = [("Generar (POST, antes de encolar)", "var(--s3)"), *series]
        titulo = "generar → estado final" if con_generar else "encolado → estado final"
        partes.append(f"<h2>Tiempo de cada trabajo ({titulo})</h2>")
        nota = f" Se muestran los primeros 80 de {len(tr['detalle'])}." if len(tr["detalle"]) > 80 else ""
        partes.append(
            f'<p class="muted">En Cola y proceso tienen la resolución del intervalo de consulta a progreso.{nota}</p>'
            '<div class="card">' + barras_apiladas(items, series) + "</div>"
        )
        partes.append(_tabla_tiempos(tr))
        partes.append(_volumen_vs_tiempo(tr["detalle"], con_generar))

    h = r["historial"]
    if len(h) >= 2:

        def serie(clave):
            return [(x.get("segundos"), x.get(clave)) for x in h]

        graficos = [
            linea("Usuarios activos", serie("usuarios"), _mmss, ""),
            linea("Requests por segundo", serie("rps"), _mmss, "req/s", 1),
            linea("p95 de los requests (ventana actual)", serie("p95_ms"), _mmss, "ms"),
            linea("Trabajos terminados (acumulado)", serie("trabajos"), _mmss, ""),
        ]
        partes.append("<h2>Evolución durante la prueba</h2>")
        partes.append('<div class="grid2">' + "".join(g for g in graficos if g) + "</div>")

    if vb:
        partes.append(_seccion_verificacion(vb))

    if r["sla"]:
        partes.append("<h2>Umbrales (provisorios, a acordar)</h2>")
        filas_sla = "".join(
            f"<tr><td>{e(s['criterio'])}</td><td class='n'>{e(s['objetivo'])}</td>"
            f"<td class='n'>{e(s['medido'])}</td><td>{estado(s['cumple'])}</td></tr>"
            for s in r["sla"]
        )
        partes.append(
            '<div class="card"><table><tr><th>Criterio</th><th class="n">Objetivo</th><th class="n">Medido</th>'
            f"<th>Resultado</th></tr>{filas_sla}</table></div>"
        )

    if r["requests"]:
        partes.append("<h2>Servicios y métricas</h2>")
        filas_req = "".join(
            f"<tr><td>{e(q['tipo'])}</td><td>{e(q['nombre'])}</td><td class='n'>{q['n']:,}</td>"
            f"<td class='n'>{q['fallas']:,}</td><td class='n'>{fmt(q['prom_ms'], 0)}</td>"
            f"<td class='n'>{fmt(q['p50_ms'], 0)}</td><td class='n'>{fmt(q['p95_ms'], 0)}</td>"
            f"<td class='n'>{fmt(q['p99_ms'], 0)}</td><td class='n'>{fmt(q['max_ms'], 0)}</td>"
            f"<td class='n'>{fmt(q['kb_prom'], 1)}</td></tr>"
            for q in r["requests"]
        )
        partes.append(
            '<div class="card"><table><tr><th>Tipo</th><th>Nombre</th><th class="n">#</th><th class="n">Fallas</th>'
            '<th class="n">prom ms</th><th class="n">p50</th><th class="n">p95</th><th class="n">p99</th>'
            f'<th class="n">máx</th><th class="n">KB prom</th></tr>{filas_req}</table></div>'
            '<p class="muted">Los percentiles de Locust están redondeados; los tiempos de trabajo de arriba son '
            "exactos (trabajos.csv).</p>"
        )

    if r["fallas"]:
        partes.append("<h2>Fallas</h2>")
        filas_f = "".join(
            f"<tr><td>{e(f['nombre'])}</td><td class='err'>{e(f['error'])}</td><td class='n'>{f['n']}</td></tr>"
            for f in r["fallas"]
        )
        partes.append(
            '<div class="card"><table><tr><th>Nombre</th><th>Error</th><th class="n">Veces</th></tr>'
            f"{filas_f}</table></div>"
        )

    if tr and tr["detalle"]:
        cols = ["inicio", "usuario", "empresa", "tipo_lote", "meses", "comprobantes_lote", "comprobantes_precheck",
                "request_id", "asientos_ok", "asientos_total", "estado_final", "s_generar", "s_total", "s_en_cola",
                "s_proceso", "s_trabajo", "control", "resultado", "errores"]  # fmt: skip
        cab = "".join(f"<th>{e(c)}</th>" for c in cols)
        cuerpo = "".join("<tr>" + "".join(f"<td>{e(f.get(c))}</td>" for c in cols) + "</tr>" for f in tr["detalle"])
        partes.append(
            f"<details><summary>Tabla de trabajos ({len(tr['detalle'])})</summary>"
            f'<div class="card"><table><tr>{cab}</tr>{cuerpo}</table></div></details>'
        )
    partes.append(
        '<p class="muted">Archivos de la corrida: run_info.json · run.log · locust_stats.csv · locust_failures.csv · '
        'historial.csv · trabajos.csv · resumen.md · <a href="locust_report.html">reporte nativo de Locust</a> · '
        '<a href="../index.html">todas las corridas</a></p>'
    )
    return pagina(f"{r['escenario_desc']} · {r['run_id']}", "".join(partes))


def _tabla_tiempos(tr: dict) -> str:
    filas = ""
    for clave, nombre in (
        ("s_generar", "Generar (POST, antes de encolar)"),
        ("s_total", "Encolado → Finalizado"),
        ("s_en_cola", "En Cola"),
        ("s_proceso", "Proceso"),
        ("s_trabajo", "Trabajo completo (generar + seguir + verificar)"),
    ):
        x = tr.get(clave) or {}
        if not x.get("n"):
            continue  # p. ej. corridas anteriores a la medición de generar
        filas += (
            f"<tr><td>{e(nombre)}</td><td class='n'>{x['n']}</td><td class='n'>{fmt(x['prom'])}</td>"
            f"<td class='n'>{fmt(x['p50'])}</td><td class='n'>{fmt(x['p90'])}</td><td class='n'>{fmt(x['p95'])}</td>"
            f"<td class='n'>{fmt(x['max'])}</td></tr>"
        )
    return (
        '<div class="card" style="margin-top:12px"><table><tr><th>Tiempo (s)</th><th class="n">n</th>'
        '<th class="n">prom</th><th class="n">p50</th><th class="n">p90</th><th class="n">p95</th><th class="n">máx</th>'
        f"</tr>{filas}</table></div>"
    )


_ICONO = {"ok": ("ok", "✓"), "atencion": ("warn", "!"), "problema": ("ko", "✕"), "info": ("na", "·")}


def lista_hallazgos(hallazgos: list[dict]) -> str:
    items = "".join(
        f'<li><span class="st {_ICONO[h["nivel"]][0]}" aria-label="{e(h["nivel"])}">{_ICONO[h["nivel"]][1]}</span>'
        f"<div><b>{e(h['titulo'])}</b> · {e(h['texto'])}</div></li>"
        for h in hallazgos
    )
    return f'<ul class="hallazgos">{items}</ul>' if items else ""


def _seccion_analisis(r: dict) -> str:
    partes = []
    if r.get("analisis"):
        partes.append(f'<div class="card analisis">{analisis.markdown_a_html(r["analisis"])}</div>')
    if r.get("hallazgos"):
        titulo = "Hallazgos automáticos" if r.get("analisis") else "Hallazgos"
        partes.append(
            f'<h3 style="margin:16px 0 8px">{titulo}</h3><div class="card">{lista_hallazgos(r["hallazgos"])}</div>'
            '<p class="muted">Calculados a partir de los datos de la corrida. El análisis escrito se edita en '
            "analisis.md, en la carpeta de la corrida.</p>"
        )
    return "<h2>Análisis y hallazgos</h2>" + "".join(partes) if partes else ""


def _seccion_verificacion(vb: dict) -> str:
    filas = "".join(
        f"<tr><td>{e(f.get('usuario'))}</td><td>{e(f.get('tipo_lote'))}</td><td class='n'>{e(f.get('empresa'))}</td>"
        f"<td class='n'>{e(f['bd_asientos_ok'])}/{e(f.get('asientos_total'))}</td>"
        f"<td class='n'>{_miles(f.get('comprobantes_lote'))}</td><td class='n'>{_miles(f['bd_comprobantes'])}</td>"
        f"<td>{estado(f['bd_coincide'], 'coincide', 'difiere')}</td></tr>"
        for f in sorted(vb["filas"], key=lambda f: _float(f.get("comprobantes_lote")) or 0)
    )
    huerfanos = ""
    for h in vb["huerfanos"]:
        if h["bd_asientos"]:
            texto = (
                f"El servidor <b>sí creó</b> {h['bd_asientos']} asientos ({h['bd_asientos_ok']} OK, desde "
                f"{e(h['bd_creados'])} UTC) y contabilizó {_miles(h['bd_comprobantes'])} comprobantes, aunque el "
                "cliente no recibió el requestId: el trabajo terminó en el servidor."
            )
        else:
            texto = "No hay asientos creados en la base para ese trabajo."
        if not h.get("bd_ultimo_de_la_fila", True):
            texto += " Hubo un trabajo posterior de la misma fila, que pudo haber reemplazado esos asientos."
        huerfanos += (
            f'<p><span class="st ko">✕ {e(h.get("usuario"))} · {e(h.get("tipo_lote"))}</span> '
            f'<span class="muted">({e(str(h.get("errores"))[:80])})</span><br>{texto}</p>'
        )
    errores = "".join(f'<p class="st ko">✕ {e(x)}</p>' for x in vb["errores"])
    return (
        "<h2>Verificación en la base</h2>"
        f'<p class="muted">Base {e(vb["base"])} · consultada {e(vb["ejecutada"])}. Por trabajo: asientos OK en '
        "nuc_AsientosOtrosModulos y comprobantes contabilizados con los GUID de esos asientos, contra lo esperado "
        "según volumen_comprobantes.csv."
        + (
            f" Se verifica el último trabajo de cada fila: {vb['reemplazados']} trabajos anteriores no se consultan "
            "porque un trabajo posterior de la misma fila reemplazó sus asientos."
            if vb.get("reemplazados")
            else ""
        )
        + "</p>"
        + (
            '<div class="card"><table><tr><th>Usuario</th><th>Tipo</th><th class="n">Empresa</th>'
            '<th class="n">Asientos OK en control</th><th class="n">Comprobantes esperados</th>'
            f'<th class="n">Comprobantes contabilizados</th><th>Resultado</th></tr>{filas}</table></div>'
            if filas
            else ""
        )
        + (f'<div class="card" style="margin-top:12px">{huerfanos}</div>' if huerfanos else "")
        + errores
    )


def _miles(v) -> str:
    n = _float(v)
    return "—" if n is None else f"{int(n):,}"


def _comprobantes(f: dict) -> str:
    lote, pre = _float(f.get("comprobantes_lote")), _float(f.get("comprobantes_precheck"))
    partes = []
    if lote is not None:
        partes.append(f"{int(lote):,} comprobantes en el lote")
    if pre is not None:
        partes.append(f"{int(pre):,} en el precheck")
    return " · ".join(partes) or "comprobantes: sin dato"


def _volumen_vs_tiempo(filas: list[dict], con_generar: bool) -> str:
    """¿La lentitud depende del volumen? Dos dispersiones: generar (o trabajo completo) y encolado→final."""
    if not any(_float(f.get("comprobantes_lote")) for f in filas):
        return ""
    clave, nombre = ("s_generar", "Generar (s)") if con_generar else ("s_trabajo", "Trabajo completo (s)")

    def puntos(campo):
        return [
            (
                _float(f.get("comprobantes_lote")),
                _float(f.get(campo)),
                f"{fmt(_float(f.get(campo)), 1, ' s')} · {int(_float(f['comprobantes_lote']) or 0):,} comprobantes\n"
                f"{f.get('usuario')} · E{f.get('empresa')} · {f.get('tipo_lote')} · {f.get('resultado')}",
                f.get("resultado") != "OK",
            )
            for f in filas
            if _float(f.get("comprobantes_lote")) is not None
        ]

    graficos = [
        dispersion(f"{nombre} según comprobantes del lote", puntos(clave), "comprobantes del lote", "s"),
        dispersion("Encolado → estado final (s) según comprobantes", puntos("s_total"), "comprobantes del lote", "s"),
    ]
    graficos = [g for g in graficos if g]
    if not graficos:
        return ""
    return (
        "<h2>¿La demora depende del volumen?</h2>"
        '<p class="muted">Cada punto es un trabajo. Comprobantes del lote: suma de los meses del trabajo según '
        "volumen_comprobantes.csv. Los trabajos con falla se marcan con ✕.</p>"
        f'<div class="grid2">{"".join(graficos)}</div>'
    )


def _float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ─────────────── índice de todas las corridas ───────────────


def indice(resumenes: list[dict], analisis_general: str | None = None) -> str:
    resumenes = sorted(resumenes, key=lambda r: r["inicio"] or "")
    partes = [
        "<h1>Pruebas de rendimiento · Crear Asiento</h1>",
        f'<p class="sub">{len(resumenes)} corridas · insumo para el informe final</p>',
    ]
    if analisis_general:
        partes.append(
            f"<h2>Análisis general</h2><div class='card analisis'>{analisis.markdown_a_html(analisis_general)}</div>"
            '<p class="muted">Texto editable en reports/analisis_general.md.</p>'
        )
    con_trabajos = [r for r in resumenes if r["trabajos"]]
    if con_trabajos:

        def etiqueta(r):
            return f"{r['parametros'].get('usuarios', '?')}u {r['inicio'][11:16]}"

        def tip(r, clave, nombre):
            tr = r["trabajos"]
            return (
                f"{fmt(tr[clave]['p95'], 1, ' s')} p95 {nombre}\n{r['run_id']}\n"
                f"{r['parametros'].get('usuarios', '?')} usuarios · {tr['ok']}/{tr['total']} trabajos OK"
            )

        partes.append("<h2>Comparación entre corridas de asientos</h2><div class='grid2'>")
        partes.append(columnas("p95 encolado → Finalizado (s)",
                               [(etiqueta(r), r["trabajos"]["s_total"]["p95"], tip(r, "s_total", "encolado → Finalizado"))
                                for r in con_trabajos], "s"))  # fmt: skip
        partes.append(columnas("p95 tiempo En Cola (s)",
                               [(etiqueta(r), r["trabajos"]["s_en_cola"]["p95"], tip(r, "s_en_cola", "En Cola"))
                                for r in con_trabajos], "s"))  # fmt: skip
        con_generar = [r for r in con_trabajos if r["trabajos"].get("s_generar", {}).get("n")]
        if con_generar:
            partes.append(columnas("p95 generar, antes de encolar (s)",
                                   [(etiqueta(r), r["trabajos"]["s_generar"]["p95"], tip(r, "s_generar", "generar"))
                                    for r in con_generar], "s"))  # fmt: skip
        partes.append("</div>")

    filas = ""
    for r in reversed(resumenes):
        p, t, tr = r["parametros"], r["total"] or {}, r["trabajos"]
        tasa = "—" if not t.get("n") else f"{t['fallas'] / t['n']:.2%}"
        duracion = "—" if r["duracion_s"] is None else _mmss(r["duracion_s"])
        trabajos_ok = f"{tr['ok']}/{tr['total']}" if tr else "—"
        filas += (
            f"<tr><td>{e(r['inicio'].replace('T', ' '))}</td>"
            f"<td><a href='{e(r['carpeta'])}/reporte.html'>{e(r['escenario_desc'])}</a>"
            f"<div class='muted'>{e(r['run_id'])}</div>"
            f"<div class='resumen-corto'>{e(analisis.resumen_corto(r))}</div></td>"
            f"<td class='n'>{e(p.get('usuarios', '—'))}</td><td class='n'>{duracion}</td>"
            f"<td class='n'>{t.get('n', 0):,}</td><td class='n'>{tasa}</td>"
            f"<td class='n'>{trabajos_ok}</td>"
            f"<td class='n'>{fmt(tr['s_total']['p95'], 1) if tr else '—'}</td>"
            f"<td class='n'>{fmt(tr['s_en_cola']['p95'], 1) if tr else '—'}</td>"
            f"<td>{estado(r['sla_cumple'])}</td></tr>"
        )
    partes.append(
        "<h2>Corridas</h2><div class='card'><table><tr><th>Inicio</th><th>Escenario</th><th class='n'>Usuarios</th>"
        "<th class='n'>Duración</th><th class='n'>Requests</th><th class='n'>% fallas</th>"
        "<th class='n'>Trabajos OK</th><th class='n'>p95 E2E (s)</th><th class='n'>p95 En Cola (s)</th>"
        f"<th>Umbrales</th></tr>{filas}</table></div>"
    )
    detalle = ""
    for r in reversed(resumenes):
        cuerpo = (analisis.markdown_a_html(r["analisis"]) if r.get("analisis") else "") + lista_hallazgos(
            r.get("hallazgos") or []
        )
        if cuerpo:
            detalle += (
                f"<details><summary><b>{e(analisis.fecha_corta(r['inicio']))} · {e(r['escenario_desc'])} · "
                f"{e(r['parametros'].get('usuarios', '?'))} usuarios</b> — "
                f"<a href='{e(r['carpeta'])}/reporte.html'>reporte</a></summary>"
                f'<div class="card analisis">{cuerpo}</div></details>'
            )
    if detalle:
        partes.append(f"<h2>Análisis y hallazgos por corrida</h2>{detalle}")
    return pagina("Corridas de rendimiento", "".join(partes))
