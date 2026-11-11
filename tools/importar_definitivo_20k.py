"""
Importación DEFINITIVA del lote 20k (empCodigo=6, periodoFiscalId=151 = 01/2026, QA7).

Hechos verificados:
  - Server rechaza bodies > ~100 KB -> chunk de 10.000 ids (90 KB) OK.
  - 1 job por empresa: Iniciar devuelve 409 IMPORT_ALREADY_RUNNING mientras hay job.
  - El fin del job se detecta por SSE con Cookie auth_token:
       GET https://gestor-comprobantes-front.../api/gdc/importacion-definitiva-status-stream?jobId=...
  - EstadoCompras {enCurso} puede quedar un tiempo en true aun con el job terminado.

Flujo: esperar idle -> ids frescos -> Iniciar/VDef/Quota/Start -> esperar job por SSE -> repetir.
"""
import sys, json, csv, time, urllib3, dotenv
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

# Raíz del proyecto = carpeta padre de scripts/ (funciona desde cualquier CWD)
HERE = str(Path(__file__).resolve().parents[1])
dotenv.load_dotenv(HERE + r"\.env")
http = urllib3.PoolManager(num_pools=20, maxsize=100, timeout=urllib3.Timeout(connect=30, read=600), retries=False)

ABP = "https://plataforma-saas-host-qa.azurewebsites.net"
GDC = "https://gestor-comprobantes-back.azurewebsites.net"
FRONT = "https://gestor-comprobantes-front.azurewebsites.net"
EMP, PID, IDOR = 6, 151, 2
CHUNK = 10000
TERMINAL = ("COMPLETED", "COMPLETED_WITH_WARNINGS", "COMPLETED_WITH_ERRORS", "FAILED", "ERROR")

# Antes: accounts/accounts_QA.csv. Ahora: la primera fila IMPO (login=plataforma) de data/qa/users.csv.
sys.path.insert(0, HERE)
from tools._cuenta import cuenta  # noqa: E402

acc = cuenta(0)

r = http.request("POST", f"{ABP}/api/TokenAuth/Authenticate",
                 headers={"Content-Type": "application/json", "Accept": "application/json", "Abp.TenantId": str(acc["tenant_id"])},
                 body=json.dumps({"userNameOrEmailAddress": acc["username"], "password": acc["password"],
                                  "rememberClient": True, "tenancyName": acc["tenancy"]}).encode())
tok = (json.loads(r.data)["result"])["accessToken"]
print(f"LOGIN {acc['tenancy']} tid={acc['tenant_id']} OK={bool(tok)}")
H = {"Authorization": f"Bearer {tok}", "Accept": "application/json", "Abp.TenantId": str(acc["tenant_id"])}


def post(path, body):
    r = http.request("POST", f"{GDC}{path}", headers={**H, "Content-Type": "application/json"},
                     body=json.dumps(body).encode())
    try: j = json.loads(r.data or "{}")
    except Exception: j = {}
    return r.status, j


def get_ids():
    r = http.request("GET", f"{GDC}/api/services/app/GdcImpoArchivo/GetLineaArchivoIdsByPeriodo"
                            f"?empCodigo={EMP}&periodo={PID}&compraVenta=C&comprobanteCertificado=COMP&idOrigen={IDOR}",
                     headers=H)
    j = json.loads(r.data or "{}")
    return [int(x) for x in (j.get("idLineaArchivo") or [])]


def en_curso():
    r = http.request("GET", f"{GDC}/api/services/app/GdcImpoArchivo/Importaciones/EstadoCompras"
                            f"?empCodigo={EMP}&periodoFiscalId={PID}", headers=H)
    try: d = (json.loads(r.data or "{}").get("data") or {})
    except Exception: d = {}
    return bool(d.get("enCurso")), d.get("estado")


def sse_wait_done(jobid, timeout=7200):
    """Abre el SSE y espera status terminal. Devuelve el ultimo JSON de estado."""
    url = f"{FRONT}/api/gdc/importacion-definitiva-status-stream?jobId={jobid}"
    hh = {"Accept": "text/event-stream", "Cache-Control": "no-cache", "Cookie": f"auth_token={tok}"}
    last = None
    t0 = time.time()
    r = http.request("GET", url, headers=hh, preload_content=False)
    buf = ""
    try:
        for ch in r.stream(120):
            buf += ch.decode("utf-8", "replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line.startswith("data:"): continue
                payload = line[5:].strip()
                if not payload: continue
                try: obj = json.loads(payload)
                except Exception: continue
                last = obj
                st = str(((obj.get("data") or {}).get("status")) or "")
                pg = ((((obj.get("data") or {}).get("progress")) or {}).get("percentComplete"))
                print(f"      [SSE] status={st} percent={pg}")
                if any(t in st.upper() for t in TERMINAL):
                    return obj
            if time.time() - t0 > timeout:
                print("      [SSE] timeout"); break
    finally:
        try: r.release_conn()
        except Exception: pass
    return last


print(f"\n### Import definitivo por chunks de {CHUNK} ###")
n_jobs = 0
total_ids = 0
started = set()
while True:
    pend = get_ids()
    ids = [i for i in pend if i not in started]
    if not ids:
        print(f"\nNo quedan ids nuevos pendientes (pendientes={len(pend)}) -> IMPORT DEFINITIVO COMPLETO.")
        break

    chunk = ids[:CHUNK]
    print(f"\n=== pendientes={len(pend)} | nuevos={len(ids)} | chunk={len(chunk)} ({chunk[0]}..{chunk[-1]}) ===")

    # gate real: Iniciar devuelve 409 mientras hay un job en curso (enCurso es stale)
    while True:
        s1, j1 = post("/api/services/app/GdcImpoArchivo/ImportacionDefinitiva/Iniciar",
                      {"empCodigo": EMP, "periodoFiscalId": PID, "idsLineaArchivo": chunk,
                       "compraVenta": "C", "comprobanteCertificado": "COMP", "idOrigen": IDOR})
        if s1 == 200:
            break
        if s1 == 409:
            print("      Iniciar 409 (job activo) -> espero 20s"); time.sleep(20); continue
        print(f"      Iniciar HTTP {s1} inesperado -> espero 20s"); time.sleep(20)
    val = ((j1.get("data") or {}).get("validatedVoucherCount"))
    print(f"   Iniciar HTTP 200 | validated={val}")
    if not val:
        print("   validated=0 -> ids ya importados, marco y sigo"); started.update(chunk); continue

    b_vd = {"empCodigo": EMP, "periodoFiscalId": PID, "idOrigen": IDOR, "compraVenta": "C",
            "idsLineaArchivo": chunk, "replaceExisting": False}
    s2, j2 = post("/api/services/app/GdcImpoArchivo/importacion/validar-definitivos", b_vd)
    comp = ((j2.get("data") or {}).get("resultado") or {}).get("compras") or {}
    print(f"   validar-definitivos HTTP {s2} | validos={comp.get('totalValidos')} rechazados={comp.get('totalRechazados')}")

    s3, j3 = post("/api/services/app/GdcImpoArchivo/CheckQuota", b_vd)
    print(f"   CheckQuota HTTP {s3} | quotaOk={((j3.get('data') or {}).get('quotaOk'))}")

    while True:
        s4, j4 = post("/api/services/app/GdcImpoArchivo/ImportacionDefinitiva/Start",
                      {"empCodigo": EMP, "periodoFiscalId": PID, "idsLineaArchivo": chunk,
                       "compraVenta": "C", "idOrigen": IDOR, "replaceExisting": False})
        if s4 == 200: break
        print(f"      Start HTTP {s4} -> espero 20s"); time.sleep(20)
    jobid = ((((j4.get("data") or {}).get("data")) or {}).get("jobId"))
    print(f"   Start HTTP 200 | jobId={jobid} accepted={(((j4.get('data') or {}).get('data')) or {}).get('acceptedVouchers')}")
    n_jobs += 1
    total_ids += len(chunk)
    started.update(chunk)

    time.sleep(15)
    res = sse_wait_done(jobid)
    if res:
        d = res.get("data") or {}
        print(f"   JOB {jobid} -> status={d.get('status')} progress={d.get('progress')}")
        print(f"      notif={d.get('notificationMessage')}")

print(f"\n### RESUMEN: jobs={n_jobs} | ids lanzados={total_ids} ===")
print(f"VERIFICACION: ids pendientes restantes = {len(get_ids())}")
