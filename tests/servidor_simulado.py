"""Servidor simulado de Holistor para probar los flujos sin QA (contratos tomados de la colección de Postman).

Simula la sesión única: cada login emite un token nuevo e invalida el anterior del mismo usuario.

Uso en tests: `ServidorSimulado().responder(...)` (en memoria, vía `ClienteSimulado`).
Uso manual, para correr Locust contra él:

    python tests/servidor_simulado.py 8089
    locust -f locustfiles/smoke_contexto.py --host http://127.0.0.1:8089 --headless -u 5 -r 5 -t 30s
    locust -f locustfiles/asiento_gdc.py --host http://127.0.0.1:8089 --headless -u 5 -r 5 -t 60s
"""

from __future__ import annotations

import itertools
import json
import sys
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

APP = "/api/services/app"
GDC = f"{APP}/GdcGenerarAsientos"


def _ok(data: Any) -> tuple[int, dict]:
    return 200, {"success": True, "data": data, "error": None}


def _error(status: int, mensaje: str) -> tuple[int, dict]:
    return status, {"success": False, "data": None, "error": {"message": mensaje, "details": None}}


def _meses(anio: int) -> list[dict]:
    import calendar

    meses = [
        {
            "codigo": f"{anio}{m:02d}",
            "desde": f"{anio}-{m:02d}-01T00:00:00",
            "hasta": f"{anio}-{m:02d}-{calendar.monthrange(anio, m)[1]:02d}T00:00:00",
            "personalizado": False,
        }
        for m in range(1, 13)
    ]
    meses.append({"codigo": f"{anio}13", "desde": "", "hasta": "", "personalizado": True})
    return meses


@dataclass
class ServidorSimulado:
    clave_valida: str | None = None  # None = acepta cualquier clave
    ejercicios: dict[int, int] = field(default_factory=lambda: {5: 2026, 6: 2027})  # codigo → año
    registros_precheck: int = 5
    fallar: dict[str, int] = field(default_factory=dict)  # ruta → status forzado (una vez)
    tokens: dict[str, str] = field(default_factory=dict)  # usuario → token vigente
    llamadas: list[tuple[str, str]] = field(default_factory=list)
    # Cola: cuántas consultas a progreso devuelve cada estado antes de Finalizado.
    consultas_en_cola: int = 1
    consultas_en_proceso: int = 1
    status_asientos: str = "OK"  # otro valor = asientos con error ("Error al crear archivo")
    trabajos: dict[str, dict] = field(default_factory=dict)
    _secuencia: Any = field(default_factory=lambda: itertools.count(1))
    _lock: Any = field(default_factory=threading.Lock)

    def invalidar_sesion(self, usuario: str) -> None:
        """Simula que el usuario inició sesión en otro lado (Postman, la UI)."""
        with self._lock:
            self.tokens[usuario] = f"otra-sesion-{next(self._secuencia)}"

    def responder(self, metodo: str, ruta: str, params: dict, body: Any, headers: dict) -> tuple[int, dict]:
        with self._lock:
            self.llamadas.append((metodo, ruta))
            if ruta in self.fallar:
                return _error(self.fallar.pop(ruta), "falla forzada")
            if ruta == f"{APP}/Account/Authenticate":
                return self._login(body or {})
            token = (headers.get("Authorization") or "").removeprefix("Bearer ")
            if token not in self.tokens.values():
                return 401, {"success": False, "error": {"message": "Current user did not login to the application!"}}
            return self._servicio(metodo, ruta, params, body or {})

    def _login(self, body: dict) -> tuple[int, dict]:
        usuario = body.get("email")
        if not usuario or not body.get("tenantId"):
            return _error(400, "faltan datos")
        if self.clave_valida is not None and body.get("password") != self.clave_valida:
            return _error(401, "Usuario o contraseña inválidos")
        token = f"tok-{usuario}-{next(self._secuencia)}"
        self.tokens[usuario] = token  # sesión única: el token anterior deja de valer
        return _ok({"accessToken": token, "expireInSeconds": 86400})

    def _servicio(self, metodo: str, ruta: str, params: dict, body: dict) -> tuple[int, dict]:
        if ruta == f"{GDC}/acceso":
            ejercicios = [
                {"codigo": c, "fechaDesde": f"{a}-01-01T00:00:00", "fechaHasta": f"{a}-12-31T00:00:00"}
                for c, a in self.ejercicios.items()
            ]
            return _ok({"ejercicios": ejercicios, "ejercicioSeleccionadoCodigo": next(iter(self.ejercicios), None)})
        if ruta == f"{GDC}/periodos":
            anio = self.ejercicios.get(int(params.get("ejCodigo", 0)))
            return _ok({"periodos": _meses(anio) if anio else []})
        if ruta == f"{APP}/GdcPeriodo/GetPeriodosFiscales":
            mes = str(body.get("search", ""))
            return _ok(
                {"items": [{"periodoFiscalCod": f"{mes[:4]}-{mes[4:]}", "periodoFiscalId": 70 + int(mes[4:] or 0)}]}
            )
        if ruta == f"{GDC}/origenes":
            return _ok(
                {
                    "origenes": [
                        {"origenAsientoId": 1, "esComprobante": True},
                        {"origenAsientoId": 2, "esComprobante": True},
                        {"origenAsientoId": 9, "esComprobante": False},
                    ]
                }
            )
        if ruta == f"{GDC}/tipos-comprobante":
            tipos = {1: ("COMPRAS", [10, 11]), 2: ("VENTAS", [20])}
            lote, ids = tipos.get(int(params.get("origenAsientoId", 0)), (None, []))
            return _ok({"tipoLote": lote, "tipos": [{"tipoComprobanteId": i} for i in ids]})
        if ruta == f"{GDC}/precheck-estructura" and metodo == "POST":
            return _ok({"registros": [{"n": i} for i in range(self.registros_precheck)]})
        if ruta == f"{GDC}/generar-asiento-comprobantes" and metodo == "POST":
            return self._generar(body)
        if ruta.startswith(f"{GDC}/crear-asiento/") and metodo == "GET":
            partes = ruta.removeprefix(f"{GDC}/crear-asiento/").split("/")
            trabajo = self.trabajos.get(partes[0])
            if trabajo is None:
                return _error(404, "requestId inexistente")
            return self._progreso(trabajo) if partes[1:] == ["progreso"] else self._resultado(trabajo)
        if ruta in (f"{GDC}/jobs/estado", f"{GDC}/resultado-proceso") and metodo == "POST":
            ids = {a.get("idAsiento") for a in body.get("asientos") or []}
            asientos = [a for t in self.trabajos.values() for a in t["asientos"] if a["idAsiento"] in ids]
            if ruta.endswith("jobs/estado"):
                rechazados = sum(1 for a in asientos if a["status"] != "OK")
                total = len(asientos)
                return _ok({"estado": "Finalizado", "total": total, "aceptados": total - rechazados,
                            "rechazados": rechazados, "pendientes": 0})  # fmt: skip
            return _ok(
                {"lineas": [{"etiqueta": f"Asiento {a['idAsiento'][:8]}", "fecha": a["fecha"]} for a in asientos]}
            )
        return _error(404, f"ruta no simulada: {metodo} {ruta}")

    # ── cola de Crear Asiento ──

    def _generar(self, body: dict) -> tuple[int, dict]:
        desde, hasta = str(body.get("fechaDesde", ""))[:7], str(body.get("fechaHasta", ""))[:7]
        meses = [m for m in _meses(int(desde[:4]))[:12] if desde <= m["desde"][:7] <= hasta] if desde else []
        if not meses:
            return _error(400, "rango sin meses")
        rid = f"req-{next(self._secuencia)}"
        asientos = [
            {
                "empresa": body["empCodigo"],
                "ejercicio": body["ejCodigo"],
                "idAsiento": str(uuid.uuid4()),
                "fecha": f"{m['hasta'][8:10]}/{m['hasta'][5:7]}/{m['hasta'][:4]}",
                "status": self.status_asientos,
            }
            for m in meses
        ]
        self.trabajos[rid] = {"consultas": 0, "asientos": asientos}
        enviados = [{k: a[k] for k in ("empresa", "ejercicio", "idAsiento")} for a in asientos]
        return 202, {"success": True, "data": {"requestId": rid, "asientos": enviados}, "error": None}

    def _progreso(self, trabajo: dict) -> tuple[int, dict]:
        trabajo["consultas"] += 1
        n = trabajo["consultas"]
        estado = "En Cola" if n <= self.consultas_en_cola else "En Proceso"
        if n > self.consultas_en_cola + self.consultas_en_proceso:
            estado = "Finalizado" if self.status_asientos == "OK" else "Error"
        return _ok({"estado": estado})

    def _resultado(self, trabajo: dict) -> tuple[int, dict]:
        asientos = [
            {**{k: a[k] for k in ("empresa", "ejercicio", "idAsiento", "status")},
             "errores": [] if a["status"] == "OK" else ["Error al crear archivo"]}
            for a in trabajo["asientos"]
        ]  # fmt: skip
        return _ok({"asientos": asientos})


# ─────────────── Cliente en memoria (reemplaza a user.client en los tests) ───────────────


class RespuestaSimulada:
    def __init__(self, status: int, cuerpo: Any):
        self.status_code = status
        self._cuerpo = cuerpo
        self.text = json.dumps(cuerpo)
        self.content = self.text.encode()
        self.error = None
        self.resultado: str | None = None  # "ok" o el mensaje de falla

    def json(self) -> Any:
        return self._cuerpo

    def success(self) -> None:
        self.resultado = "ok"

    def failure(self, mensaje: str) -> None:
        self.resultado = mensaje

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


class ClienteSimulado:
    def __init__(self, servidor: ServidorSimulado):
        self.servidor = servidor
        self.respuestas: list[tuple[str, RespuestaSimulada]] = []  # (name, respuesta)

    def request(self, method, url, name=None, json=None, params=None, headers=None, **_kw):
        status, cuerpo = self.servidor.responder(method, url, params or {}, json, headers or {})
        resp = RespuestaSimulada(status, cuerpo)
        self.respuestas.append((name, resp))
        return resp

    def fallas(self) -> list[str]:
        return [r.resultado for _, r in self.respuestas if r.resultado not in (None, "ok")]


# ─────────────── Servidor HTTP real (para correr Locust contra él) ───────────────


def servir(servidor: ServidorSimulado, puerto: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _atender(self, metodo: str) -> None:
            partes = urlsplit(self.path)
            params = {k: v[0] for k, v in parse_qs(partes.query).items()}
            largo = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(largo) or b"null") if largo else None
            status, cuerpo = servidor.responder(metodo, partes.path, params, body, dict(self.headers))
            datos = json.dumps(cuerpo).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def do_GET(self):  # noqa: N802
            self._atender("GET")

        def do_POST(self):  # noqa: N802
            self._atender("POST")

        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", puerto), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8089
    srv = ServidorSimulado()
    httpd = servir(srv, puerto)
    print(f"Servidor simulado en http://127.0.0.1:{puerto} (Ctrl+C para salir)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        httpd.shutdown()
        print(f"{len(srv.llamadas)} llamadas atendidas")
