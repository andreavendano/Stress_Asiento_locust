"""Servidor simulado de los escenarios de comprobantes (importación, modificación masiva y crear comprobante).

Imita los contratos que usa el proyecto original (stress_test): login de la plataforma con sesión única,
datos maestros, grilla de compras, importación (archivo, líneas, job y stream SSE), modificación masiva y
alta/lectura de comprobantes. Atiende todos los "hosts" (plataforma, portal, front y back) en el mismo lugar:
solo mira la ruta.

Uso en tests: `ClienteComprobantes(ServidorComprobantes())` reemplaza a user.client.
Uso manual, para correr Locust contra él (todos los hosts apuntan al mismo puerto):

    python tests/servidor_comprobantes.py 8090
    $env:HOLISTOR_QA_CLAVE = "x"
    $env:HOLISTOR__PLATAFORMA__HOST_URL = "http://127.0.0.1:8090"
    $env:HOLISTOR__PLATAFORMA__PORTAL_URL = "http://127.0.0.1:8090"
    $env:HOLISTOR__PLATAFORMA__FRONT_URL = "http://127.0.0.1:8090"
    locust -f locustfiles/importacion_compras.py --host http://127.0.0.1:8090 --headless -u 2 -r 2 -t 60s \
        --trabajos-por-usuario 1
"""

from __future__ import annotations

import itertools
import json
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

APP = "/api/services/app"
CPBTE = "/api/service/ComprobantesCompra"


def _ok(data: Any = None, **raiz) -> tuple[int, dict]:
    return 200, {"success": True, "data": data, "error": None, **raiz}


def _error(status: int, mensaje: str) -> tuple[int, dict]:
    return status, {"success": False, "data": None, "error": {"message": mensaje, "details": None}}


@dataclass
class ServidorComprobantes:
    tenants: dict[str, int] = field(default_factory=lambda: {"GDCpruebasQA7": 867, "GDCpruebasQA6": 866})
    clave_valida: str | None = None  # None = acepta cualquier clave
    empresas: tuple[int, ...] = (6,)
    periodos: dict[str, int] = field(default_factory=lambda: {"202601": 151, "202602": 6})
    proveedores: list[dict] = field(default_factory=lambda: [
        {"clienteProveedorId": 24474, "clienteProveedorProveedor": True, "activo": True, "tipoDocAbrev": "CUIT",
         "tipoDocumentoId": 80, "clienteProveedorNroDoc": "30-71595431-8", "clienteProveedorRzSocial": "PROV SA"},
    ])  # fmt: skip
    comprobantes_iniciales: int = 3  # comprobantes de compra que ya tiene cada empresa/período
    consultas_archivo: int = 1  # consultas a GetEstadoArchivo antes de finalizado
    job_status: str = "COMPLETED"
    lineas_con_error: int = 0  # líneas del archivo rechazadas por el backend
    crear_sin_id: bool = False  # alta de comprobante devuelve saved=False (duplicado)
    fallar: dict[str, int] = field(default_factory=dict)  # ruta → status forzado (una vez)
    llamadas: list[tuple[str, str]] = field(default_factory=list)
    tokens: dict[tuple[int, str], str] = field(default_factory=dict)
    _seq: Any = field(default_factory=lambda: itertools.count(1))
    _lock: Any = field(default_factory=threading.RLock)
    cpbtes: dict[tuple[int, str], list[dict]] = field(default_factory=dict)  # (emp, AAAA-MM) → comprobantes
    archivos: dict[int, dict] = field(default_factory=dict)
    temporales: dict[str, dict] = field(default_factory=dict)
    jobs: dict[str, dict] = field(default_factory=dict)

    def invalidar_sesion(self, tenant: int, usuario: str) -> None:
        with self._lock:
            self.tokens[(tenant, usuario)] = f"otra-sesion-{next(self._seq)}"

    # ───────────── despacho ─────────────

    def responder(self, metodo: str, url: str, params: dict, body: Any, headers: dict, data: bytes | None = None):
        partes = urlsplit(url)
        ruta = partes.path
        params = {**{k: v[0] for k, v in parse_qs(partes.query).items()}, **(params or {})}
        with self._lock:
            self.llamadas.append((metodo, ruta))
            if ruta in self.fallar:
                return _error(self.fallar.pop(ruta), "falla forzada")
            if ruta == f"{APP}/Account/IsTenantAvailable":
                tid = self.tenants.get((body or {}).get("tenancyName"))
                return 200, {"success": True, "result": {"state": 1 if tid else 3, "tenantId": tid}}
            if ruta == "/api/TokenAuth/Authenticate":
                return self._login(body or {}, headers)
            token = (headers.get("Authorization") or "").removeprefix("Bearer ")
            if token not in self.tokens.values():
                return 401, {"success": False, "error": {"message": "Token no válido"}}
            return self._servicio(metodo, ruta, params, body or {}, data, headers)

    def _login(self, body: dict, headers: dict):
        tenant = int(headers.get("Abp.TenantId") or 0)
        usuario = body.get("userNameOrEmailAddress")
        if not tenant or not usuario:
            return _error(400, "faltan datos")
        if self.clave_valida is not None and body.get("password") != self.clave_valida:
            # ABP: credenciales inválidas con HTTP 500
            error = {"message": "Inicio de sesión fallido", "details": "Nombre de usuario o contraseña incorrecta"}
            return 500, {"success": False, "error": error}
        token = f"tok-{tenant}-{usuario}-{next(self._seq)}"
        self.tokens[(tenant, usuario)] = token  # sesión única
        return 200, {"success": True, "result": {"accessToken": token, "userId": 5, "expireInSeconds": 86400}}

    def _lista_cpbtes(self, emp: int, periodo_guion: str) -> list[dict]:
        clave = (int(emp), periodo_guion)
        if clave not in self.cpbtes:
            self.cpbtes[clave] = [self._nuevo_cpbte() for _ in range(self.comprobantes_iniciales)]
        return self.cpbtes[clave]

    def _nuevo_cpbte(self) -> dict:
        return {"cCpraId": 1000 + next(self._seq), "condFiscal": 1, "provin": 1}

    def _servicio(self, metodo, ruta, params, body, data, headers):  # noqa: C901 (un despacho por ruta)
        # ── maestros
        if ruta == f"{APP}/Empresas/GetEmpresasByTenant":
            return _ok({"items": [{"empCodigo": e, "empRazon": f"EMPRESA {e}"} for e in self.empresas]})
        if ruta == f"{APP}/GdcPeriodo/GetPeriodosFiscales":
            emp = (body.get("filter") or {}).get("empCodigo")
            return _ok({"items": [{"empCodigo": emp, "periodoFiscalId": i, "periodoFiscalCod": c}
                                  for c, i in self.periodos.items()]})  # fmt: skip
        if ruta == f"{APP}/GdcLookups/GdcClienteProveedor/Consulta":
            return _ok({"items": self.proveedores})
        if ruta == f"{APP}/GdcLookups/getMovimientoTipoConsultaLookup":
            return _ok({"items": [{"movimientoTipoId": 1404}, {"movimientoTipoId": 1405}]})
        # ── grilla de compras
        if ruta == f"{APP}/GdcComprobanteCompra/getGrid":
            periodo = (body.get("filter") or {}).get("periodoFiscalCodDesde") or ""
            if len(periodo) == 6:  # el flujo completo la pide con AAAAMM
                periodo = f"{periodo[:4]}-{periodo[4:]}"
            todos = self._lista_cpbtes(body.get("empCodigo"), periodo)
            pag, lim = int(body.get("page") or 1), int(body.get("limit") or 10)
            return _ok({"items": todos[(pag - 1) * lim : pag * lim], "total": len(todos)})
        # ── importación
        if ruta.startswith(f"{APP}/GdcImpoOrigen/GetListForImport"):
            return _ok({"data": [{"CodigoOrigen": "PIC", "IdOrigen": 2, "Descripcion": "Portal IVA",
                                  "NombreArchivo": "comprobantes_periodo_<PERIODO>_compras", "Extension": "csv",
                                  "CaracterDelimitador": ";"}]})  # fmt: skip
        if ruta == f"{APP}/GdcImpoArchivo/Importaciones/EstadoCompras":
            return _ok({"enCurso": False})
        if ruta == f"{APP}/GdcImpoArchivo/SelectFile":
            return self._select_file(data or b"")
        if ruta == f"{APP}/GdcImpoArchivo/ValidatePreliminary":
            if body.get("fileTempId") not in self.temporales:
                return _error(400, "fileTempId inexistente")
            return 200, {"success": True, "canProceed": True, "validation": {"estructura": True, "encabezado": True}}
        if ruta == f"{APP}/GdcImpoArchivo/Incorporar":
            tmp = self.temporales[body["fileTempId"]]
            ida = next(self._seq)
            lineas = [{"idArchivo": ida, "idLineaArchivo": ida * 1000 + i,
                       "estado": "E" if i < self.lineas_con_error else "O",
                       "mensajeError": "CUIT inválido" if i < self.lineas_con_error else None}
                      for i in range(tmp["filas"])]  # fmt: skip
            self.archivos[ida] = {"lineas": lineas, "consultas": 0, "emp": body["empCodigo"],
                                  "periodo_id": body["periodoId"]}  # fmt: skip
            return _ok({"idArchivo": ida})
        if ruta == f"{APP}/GdcImpoArchivo/GetEstadoArchivo":
            a = self.archivos[body["idArchivo"]]
            a["consultas"] += 1
            fin = a["consultas"] > self.consultas_archivo
            return 200, {"success": True, "finalizado": fin, "estadoArchivo": "PROCESADO" if fin else "PROCESANDO",
                         "totalLineas": len(a["lineas"]), "lineasProcesadas": len(a["lineas"]) if fin else 0}
        if ruta == f"{APP}/GdcImpoArchivo/GetSummaryImport":
            lineas = self.archivos[body["idArchivo"]]["lineas"]
            ok = sum(1 for ln in lineas if ln["estado"] == "O")
            return 200, {"success": True, "summary": {"totalRegistros": len(lineas), "totalOk": ok, "totalWarning": 0,
                                                       "totalError": len(lineas) - ok, "totalSeleccionables": ok}}
        if ruta == f"{APP}/GdcImpoArchivo/GetListComprobantes":
            ida = (body.get("filter") or {}).get("idArchivo")
            lineas = self.archivos.get(ida, {}).get("lineas", [])
            pag, lim = int(body["page"]), int(body["limit"])
            if lim > 100:
                return _error(400, "limit must not be greater than 100")
            return 200, {"success": True, "data": lineas[(pag - 1) * lim : pag * lim], "total": len(lineas)}
        if ruta == f"{APP}/GdcImpoArchivo/ImportacionDefinitiva/Iniciar":
            return _ok({"existingVouchersInfo": {"compraCount": 0}})
        if ruta == f"{APP}/GdcImpoArchivo/importacion/validar-definitivos":
            n = len(body.get("idsLineaArchivo") or [])
            return _ok({"resultado": {"compras": {"totalProcesados": n, "totalValidos": n, "totalRechazados": 0}}})
        if ruta == f"{APP}/GdcImpoArchivo/CheckQuota":
            return _ok({"quotaOk": True, "excedeCuota": False})
        if ruta == f"{APP}/GdcImpoArchivo/ImportacionDefinitiva/Start":
            ids = body.get("idsLineaArchivo") or []
            job = f"job-{next(self._seq)}"
            cod = next(c for c, i in self.periodos.items() if i == body["periodoFiscalId"])
            self.jobs[job] = {"n": len(ids), "emp": body["empCodigo"], "periodo": f"{cod[:4]}-{cod[4:]}",
                              "aplicado": False}  # fmt: skip
            return _ok({"data": {"jobId": job, "acceptedVouchers": len(ids)}})
        if ruta == "/api/gdc/importacion-definitiva-status-stream":
            return self._stream(params.get("jobId"), headers)
        # ── modificación masiva
        if ruta == f"{APP}/GdcPeriodoFiscal/protegido":
            return _ok({"protegido": False})
        if ruta == f"{CPBTE}/periodo-protegido":
            return _ok({"protegido": False})
        if ruta == f"{CPBTE}/modificacion-masiva/condiciones-iva":
            return _ok([{"codigo": 1, "abreviatura": "RI"}, {"codigo": 4, "abreviatura": "EX"}])
        if ruta == f"{CPBTE}/modificacion-masiva/provincias":
            return _ok([{"codigo": 1, "nombre": "BUENOS AIRES"}, {"codigo": 18, "nombre": "FORMOSA"}])
        if ruta == f"{CPBTE}/modificacion-masiva/cabecera":
            todos = self._lista_cpbtes(body["empCodigo"], body["periodoFiscalCodDesde"])
            ids = set(body.get("ccpraIds") or [])
            for c in todos:
                if (c["cCpraId"] in ids) != bool(body.get("isExclude")):
                    c["condFiscal"], c["provin"] = body["CCpraCondFiscal"], body["CCpraProvin"]
            return _ok({"mensaje": "Proceso de modificación finalizado."})
        # ── crear / leer comprobante
        if ruta == CPBTE and metodo == "POST":
            if self.crear_sin_id:
                return _ok({"saved": False, "ccpraId": 0, "duplicateWarning": {"code": "DUPLICATE_VOUCHER"}})
            cab = body.get("cabecera") or {}
            cod = next((c for c, i in self.periodos.items() if i == cab.get("CCpraPeriodoFiscal")), "202601")
            nuevo = self._nuevo_cpbte()
            self._lista_cpbtes(cab.get("empCodigo"), f"{cod[:4]}-{cod[4:]}").append(nuevo)
            return _ok({"ccpraId": nuevo["cCpraId"], "saved": True})
        if ruta.startswith(f"{CPBTE}/") and metodo == "GET":
            cid = ruta.rsplit("/", 1)[-1]
            existe = any(str(c["cCpraId"]) == cid for lst in self.cpbtes.values() for c in lst)
            return _ok({"cCpraId": int(cid)}) if existe else _error(404, "no existe")
        # ── navegación (páginas, banners, lookups que el flujo no usa)
        return _ok({})

    def _select_file(self, data: bytes):
        texto = data.decode("iso-8859-1")
        if 'name="file"' not in texto:
            return _error(400, "falta el archivo")
        archivo = texto.split('name="file"', 1)[1].split("\r\n\r\n", 1)[1].rsplit("\r\n--", 1)[0]
        filas = max(0, len([ln for ln in archivo.split("\r\n") if ln.strip()]) - 1)
        tmp = f"tmp-{next(self._seq)}"
        self.temporales[tmp] = {"filas": filas}
        return 200, {"success": True, "fileInfo": {"fileTempId": tmp}}

    def _stream(self, job_id: str, headers: dict):
        job = self.jobs.get(job_id)
        if job is None:
            return 404, "job inexistente"
        if not job["aplicado"]:
            job["aplicado"] = True
            if self.job_status.startswith("COMPLETED"):
                lst = self._lista_cpbtes(job["emp"], job["periodo"])
                lst.extend(self._nuevo_cpbte() for _ in range(job["n"]))
        fin = {"status": self.job_status, "finishedAt": "2026-01-01T00:00:00Z", "errors": [],
               "progress": {"processedVouchers": job["n"], "totalVouchers": job["n"], "failedVouchers": 0}}  # fmt: skip
        eventos = [": ping", 'data: {"data": {"status": "PROCESSING"}}', "data: " + json.dumps({"data": fin})]
        return 200, ("SSE", eventos)


# ─────────────── Cliente en memoria (reemplaza a user.client en los tests) ───────────────


class RespuestaComprobantes:
    def __init__(self, status: int, cuerpo: Any):
        self.status_code = status
        self.error = None
        self.encoding = None
        self.resultado: str | None = None
        self._eventos = None
        if isinstance(cuerpo, tuple) and cuerpo and cuerpo[0] == "SSE":
            self._eventos = cuerpo[1]
            self._cuerpo = None
            self.text = "\n".join(cuerpo[1])
        else:
            self._cuerpo = cuerpo
            self.text = cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo)
        self.content = self.text.encode()

    def json(self):
        if self._cuerpo is None or isinstance(self._cuerpo, str):
            raise ValueError("no es JSON")
        return self._cuerpo

    def iter_lines(self, decode_unicode=False):
        yield from self._eventos or []

    def success(self):
        self.resultado = "ok"

    def failure(self, mensaje):
        self.resultado = mensaje

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Cookies(dict):
    def set(self, nombre, valor, domain=None):
        self[nombre] = valor


class ClienteComprobantes:
    def __init__(self, servidor: ServidorComprobantes):
        self.servidor = servidor
        self.cookies = _Cookies()
        self.respuestas: list[tuple[str, RespuestaComprobantes]] = []

    def request(self, method, url, name=None, json=None, params=None, headers=None, data=None, **_kw):
        status, cuerpo = self.servidor.responder(method, url, params or {}, json, headers or {}, data)
        resp = RespuestaComprobantes(status, cuerpo)
        self.respuestas.append((name, resp))
        return resp

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def nombres(self) -> list[str]:
        return [n for n, _ in self.respuestas]

    def fallas(self) -> list[str]:
        return [r.resultado for _, r in self.respuestas if r.resultado not in (None, "ok")]


# ─────────────── Servidor HTTP real (para correr Locust contra él) ───────────────


def servir(servidor: ServidorComprobantes, puerto: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _atender(self, metodo: str) -> None:
            largo = int(self.headers.get("Content-Length") or 0)
            crudo = self.rfile.read(largo) if largo else b""
            body, data = None, None
            if "multipart/form-data" in (self.headers.get("Content-Type") or ""):
                data = crudo
            elif crudo:
                body = json.loads(crudo)
            status, cuerpo = servidor.responder(metodo, self.path, {}, body, dict(self.headers), data)
            if isinstance(cuerpo, tuple) and cuerpo[0] == "SSE":
                datos, tipo = ("\n\n".join(cuerpo[1]) + "\n\n").encode(), "text/event-stream"
            elif isinstance(cuerpo, str):
                datos, tipo = cuerpo.encode(), "text/plain"
            else:
                datos, tipo = json.dumps(cuerpo).encode(), "application/json"
            self.send_response(status)
            self.send_header("Content-Type", tipo)
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
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    srv = ServidorComprobantes()
    httpd = servir(srv, puerto)
    print(f"Servidor simulado de comprobantes en http://127.0.0.1:{puerto} (Ctrl+C para salir)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        httpd.shutdown()
        print(f"{len(srv.llamadas)} llamadas atendidas")
