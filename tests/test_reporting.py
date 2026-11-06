"""Informe por corrida (resumen.json / resumen.md / reporte.html) e índice, a partir de los archivos."""

import csv
import json

from holistor_stress.reporting import informe
from holistor_stress.reporting.html import _escala
from holistor_stress.reporting.resumen import construir_resumen, percentil
from holistor_stress.reporting.trabajos import RegistroTrabajos, ResultadoTrabajo

CAB = ["Type", "Name", "Request Count", "Failure Count", "Median Response Time", "Average Response Time",
       "Min Response Time", "Max Response Time", "Average Content Size", "Requests/s", "Failures/s", "50%", "66%",
       "75%", "80%", "90%", "95%", "98%", "99%", "99.9%", "99.99%", "100%"]  # fmt: skip


def _stats(*filas):
    return [CAB, *[[t, n, c, f, 10, 10, 1, 20, 100, 1, 0] + [p] * 11 for t, n, c, f, p in filas]]


def _corrida(carpeta, usuarios=5, trabajos=((3.0, 1.0, "OK"), (5.0, 2.0, "FALLA")), corrupta=False):
    carpeta.mkdir(parents=True)
    info = {
        "run_id": carpeta.name,
        "ambiente": "qa",
        "base_url": "https://qa.test",
        "inicio": f"2026-11-05T10:0{usuarios % 10}:00",
        "fin": "2026-11-05T10:30:00",
        "duracion_s": 1800,
        "exit_code": 1,
        "parametros": {"locustfile": "locustfiles/asiento_gdc.py", "usuarios": usuarios, "spawn_rate": 1},
        "thresholds": {
            "error_rate_max": 0.0,
            "p95_ms": {"[Auth] Authenticate": 3000},
            "e2e_p95_s": {"[E2E] GDC encolado→Finalizado": 4},
        },  # fmt: skip
    }
    (carpeta / "run_info.json").write_text(json.dumps(info), encoding="utf-8")
    filas = _stats(
        ("POST", "[Auth] Authenticate", 5, 0, 2500),
        ("GET", "[GDC] acceso", 10, 1, 100),
        ("E2E", "[E2E] GDC encolado→Finalizado", 2, 1, 5000),
        ("", "Aggregated", 17, 2, 900),
    )
    if corrupta:
        filas.insert(2, ["", "950", "950", "950", "950"])
    with (carpeta / "locust_stats.csv").open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(filas)
    reg = RegistroTrabajos(carpeta / "trabajos.csv")
    for i, (cola, proc, res) in enumerate(trabajos):
        reg.registrar(
            ResultadoTrabajo(
                inicio=f"2026-11-05T10:0{i}:00",
                fila=f"F{i}",
                tenant=866,
                usuario=f"GDC{i}",
                modulo="GDC",
                empresa=3064,
                asientos_total=6,
                asientos_ok=6 if res == "OK" else 0,
                estado_final="Finalizado",
                s_total=cola + proc,
                s_en_cola=cola,
                s_proceso=proc,
                s_trabajo=cola + proc + 1,
                resultado=res,
                errores=[] if res == "OK" else ["6 de 6 asientos no OK: Error al crear archivo"],
            )  # fmt: skip
        )
    return carpeta


def test_resumen_desde_archivos(tmp_path):
    r = construir_resumen(_corrida(tmp_path / "run1"))
    assert r["escenario"] == "asiento_gdc" and r["total"]["n"] == 17
    tr = r["trabajos"]
    assert (tr["total"], tr["ok"], tr["falla"], tr["asientos_ok"]) == (2, 1, 1, 6)
    assert tr["s_total"]["p95"] == 7.0 and tr["s_en_cola"]["max"] == 5.0
    sla = {s["criterio"]: s["cumple"] for s in r["sla"]}
    assert sla == {
        "Tasa de error HTTP": False,  # 1 falla en 15 requests HTTP (las E2E no cuentan)
        "p95 [Auth] Authenticate": True,
        "p95 [E2E] GDC encolado→Finalizado": False,
    }
    assert r["sla_cumple"] is False


def test_filas_corruptas_del_csv_nativo_se_descartan(tmp_path):
    r = construir_resumen(_corrida(tmp_path / "run1", corrupta=True))
    assert [q["nombre"] for q in r["requests"]] == [
        "[Auth] Authenticate",
        "[GDC] acceso",
        "[E2E] GDC encolado→Finalizado",
    ]


def test_genera_md_html_e_indice(tmp_path):
    raiz = tmp_path / "reports"
    _corrida(raiz / "run1", usuarios=1)
    _corrida(raiz / "run5", usuarios=5)
    (raiz / "otra-cosa").mkdir()  # sin run_info.json: se ignora
    assert informe.main(["--reportes", str(raiz)]) == 0
    for run in ("run1", "run5"):
        md = (raiz / run / "resumen.md").read_text(encoding="utf-8")
        assert "**1 de 2 trabajos OK**" in md and "❌ no cumple" in md
        html = (raiz / run / "reporte.html").read_text(encoding="utf-8")
        assert "Tiempo de cada trabajo" in html and "✕ falla" in html
        assert json.loads((raiz / run / "resumen.json").read_text(encoding="utf-8"))["trabajos"]["total"] == 2
    indice = (raiz / "index.html").read_text(encoding="utf-8")
    assert "run1/reporte.html" in indice and "run5/reporte.html" in indice and "otra-cosa" not in indice
    tabla = indice[indice.index("<h2>Corridas") :]
    assert tabla.index("run5") < tabla.index("run1")  # en la tabla, la más reciente primero


def test_html_escapa_textos(tmp_path):
    c = _corrida(tmp_path / "run1", trabajos=((1.0, 1.0, "FALLA"),))
    (c / "trabajos.csv").write_text(
        (c / "trabajos.csv").read_text(encoding="utf-8-sig").replace("Error al crear archivo", "<script>x</script>"),
        encoding="utf-8",
    )
    informe.generar_corrida(c)
    assert "<script>x</script>" not in (c / "reporte.html").read_text(encoding="utf-8")


def test_percentil_y_escala():
    assert percentil([1, 2, 3, 4], 50) == 2 and percentil([5], 95) == 5 and percentil([], 95) is None
    assert _escala(3.7) == (4.0, [0.0, 1.0, 2.0, 3.0, 4.0])
    assert _escala(5000, 3)[0] == 6000


def test_markdown_listas_anidadas_y_tablas():
    from holistor_stress.reporting.analisis import markdown_a_html

    html = markdown_a_html("1. **Uno**\n   - a\n   - b\n2. Dos <x>\n\n| A | B |\n|---|---|\n| 1 | `c` |\n\nFin")
    assert html == (
        "<ol><li><b>Uno</b><ul><li>a</li><li>b</li></ul></li><li>Dos &lt;x&gt;</li></ol>"
        '<table class="md"><tr><th>A</th><th>B</th></tr><tr><td>1</td><td><code>c</code></td></tr></table><p>Fin</p>'
    )


def test_hallazgos_automaticos_y_analisis_escrito(tmp_path):
    from holistor_stress.reporting.analisis import resumen_corto

    carpeta = _corrida(tmp_path / "run1")
    (carpeta / "analisis.md").write_text("Primera línea del análisis.\n\n### Detalle\n- punto", encoding="utf-8")
    r = informe.generar_corrida(carpeta)
    titulos = [h["titulo"] for h in r["hallazgos"]]
    assert titulos[0] == "Resultado de los trabajos" and "Umbral no cumplido" in titulos
    assert resumen_corto(r) == "Primera línea del análisis."
    html = (carpeta / "reporte.html").read_text(encoding="utf-8")
    assert "Análisis y hallazgos" in html and "<li>punto</li>" in html
    md = (carpeta / "resumen.md").read_text(encoding="utf-8")
    assert "## Análisis" in md and "## Hallazgos automáticos" in md
    (tmp_path / "analisis_general.md").write_text("Conclusión general.", encoding="utf-8")
    informe.generar_indice(tmp_path)
    assert "Conclusión general." in (tmp_path / "index.html").read_text(encoding="utf-8")
