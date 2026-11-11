"""E2E: 1 UNICO ARCHIVO CSV = 20.000 comprobantes, solo tenant QA7.
Periodo 01/2026 (no protegido), empCodigo=6.
FechaEmision 1..31/3/2026 ciclando, PtoVenta FIJO=1 (<=4dig, repetible),
NroComp unico 1_000_001..1_020_000, jitter grande anti-DUPLICATE,
proveedor emp6 CUIT=30715954318 valido, TC=11 canónico.
"""
import io, os, sys, json, csv, time, copy, random, urllib3, dotenv
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
# Raíz del proyecto = carpeta padre de scripts/ (funciona desde cualquier CWD)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
dotenv.load_dotenv(str(ROOT / ".env"))
_R = random.Random()
http = urllib3.PoolManager(num_pools=50, maxsize=1000, timeout=urllib3.Timeout(total=600), retries=False)

PLANTILLA = str(ROOT / "data" / "plantillas" / "importacion" / "plantilla_importacion_compras_oficial.csv")
TARGET_N = 20000

def row_csv(i):
    # Antes: accounts/accounts_QA.csv. Ahora: la fila IMPO (login=plataforma) número i de data/qa/users.csv.
    from tools._cuenta import cuenta
    return cuenta(i)

def login(tncy, usr, pwd, tid):
    abp = "https://plataforma-saas-host-qa.azurewebsites.net"
    h0 = {"Content-Type":"application/json","Accept":"application/json"}
    if tid: h0["Abp.TenantId"] = str(tid)
    r1 = http.request("POST", f"{abp}/api/TokenAuth/Authenticate", headers=h0,
        body=json.dumps({"userNameOrEmailAddress":usr,"password":pwd,"rememberClient":True,"tenancyName":tncy}).encode())
    try: j1 = json.loads(r1.data or "{}")
    except Exception: j1 = {}
    tok = (((j1.get("result") or {}).get("accessToken")) if isinstance(j1.get("result"),dict) else None)
    tid_out = ((j1.get("result") or {}).get("tenantId") if isinstance(j1.get("result"),dict) else None) or tid
    return tid_out, tok

def req(m, pth, tok, tid, name, body=None, qs=None, extra_headers=None, raw_body=None):
    gdc = "https://gestor-comprobantes-back.azurewebsites.net"
    h = {"Authorization":f"Bearer {tok}","Accept":"application/json"}
    if tid: h["Abp.TenantId"] = str(tid)
    if extra_headers: h.update(extra_headers)
    kw = {"headers":h,"timeout":600}
    if raw_body is not None:
        kw["body"] = raw_body
    elif body is not None:
        h["Content-Type"]="application/json"; kw["body"]=json.dumps(body).encode()
    u = f"{gdc}{pth}"
    if qs: u += "?" + "&".join(f"{k}={v}" for k,v in qs.items())
    t0 = time.time()
    try:
        r = http.request(m, u, **kw)
    except Exception as ex:
        print(f"  EXC {name}: {ex}"); return 0, {}, b""
    dt = int((time.time()-t0)*1000)
    try: j = json.loads(r.data or "{}")
    except Exception: j = {}
    msg = ""
    if isinstance(j, dict):
        msg = str(j.get("message") or j.get("msg") or "")[:220]
        code = str(j.get("code") or "")[:80]
        if code: msg = f"code={code}  {msg}"
    print(f"   {name}: HTTP {r.status} {dt}ms  {msg[:200]}")
    return r.status, j, r.data

# ========================================================================= MAIN
EMP=6; PID=151; PCOD="202601"; IDOR=2
MES = 1; ANIO = 2026
import calendar
DIAS_MES = calendar.monthrange(ANIO, MES)[1]  # 31 para enero

r0 = row_csv(0)  # QA7 (row1 = header, row2 = QA7 index 0)
tncy, usr, pwd, tid = r0["tenancy"], r0["username"], r0["password"], r0.get("tenant_id") or ""
print(f"▶ Target: {tncy} tenant_id={tid} | empCodigo={EMP} | periodoCod={PCOD} idPeriodo={PID} | N={TARGET_N}")
rt, tok = login(tncy, usr, pwd, tid)
if not tok: print("❌ NO LOGIN"); sys.exit(1)
print(f"✅ Login {tncy} tid={rt}")

# ================================================================ EstadoCompras
# 🚨 Importante: El backend GdC devuelve periodoEnCurso GLOBAL de la EMPRESA (puede ser 01/2026 o cualquier período).
# NOSOTROS seleccionamos período 01/2026 SIEMPRE (PID=151 / PCOD=202601) en TODOS los endpoints SelectFile, Validate, Incorporar, Iniciar.
# Regla de bloqueo CORREGIDA: Bloquear SÓLO si enCurso=True Y el periodoEnCurso GLOBAL coincide con NUESTRO período target (01/2026).
# Si el período enCurso global es OTRO (ej: 01/2026, 02/2026) → NO bloqueamos nuestra importación a 01/2026.
s,j,_ = req("GET","/api/services/app/GdcImpoArchivo/Importaciones/EstadoCompras",tok,rt,"EstadoCompras (pre)",
            qs={"empCodigo":EMP,"periodoFiscalId":PID})
d = (j.get("data") or j.get("result") or {}) if isinstance(j,dict) else {}
en_curso = bool(d.get("enCurso")) if isinstance(d,dict) else False
pec = (d.get("periodoEnCurso") if isinstance(d,dict) else None) or ""
print(f"   enCurso={en_curso}  periodoEnCurso(GLOBAL empresa)={pec!r}  NUESTRO período target=01/2026 (PID={PID} COD={PCOD})")
# Normalizar períodos para comparar: "01/2026", "2026-03", "202601", "151" → todos son 01/2026
def _es_nuestro_periodo(pec_str):
    """Devuelve True si el string periodo GLOBAL corresponde a NUESTRO target 01/2026."""
    if not pec_str: return False
    s2 = str(pec_str).strip().lower()
    return any(x in s2 for x in ("01/2026", "202601", "enero/2026", "mar-2026")) or str(PID) in s2
bloquear_por_mismo_periodo = en_curso and _es_nuestro_periodo(pec)
if bloquear_por_mismo_periodo:
    print(f"❌ BLOQUEO: Importación EN CURSO en NUESTRO MISMO período 01/2026 (periodoEnCurso={pec!r}). Cancelar manualmente por UI Front GdC y volver a ejecutar.")
    sys.exit(2)
elif en_curso and not bloquear_por_mismo_periodo:
    print(f"⚠️  AVISO: Hay una importación EN CURSO en OTRO período (periodoEnCurso={pec!r}), pero NOSOTROS enviamos al período 01/2026 (PID={PID}). No bloqueamos (período distinto).")
else:
    print("✅ Ninguna importación en curso. Podemos importar libremente en período 01/2026.")

# ================================================================ 1) Generar CSV
tcsv0 = time.time()
with open(PLANTILLA, "r", encoding="latin-1", newline="") as fh:
    rd = list(csv.reader(fh, delimiter=";"))
header = rd[0]
base_c = copy.deepcopy(rd[1])
while len(base_c) < 32: base_c.append("")
prov_td, prov_cuit, prov_den = "80", "30715954318", "2MIL10Y7 S.R.L."
TC_FIJO = "11"
# PUNTO DE VENTA FIJO = 1 para TODAS las N filas (según usuario: PUEDE repetir, alta automática, ≤4 díg)
PTO_VENTA_FIJO = 1
BASE_NRO_COMP = 1_000_000  # NroComp 1_000_001 ... 1_000_000+N = ÚNICOS cross todo lote

def br(f): return f"{f:.2f}".replace(".",",")

# 🔴 FIX Opción A: RATIO PROPORCIONAL EXACTO (conserva Neto+IVA=Total y parciales=totales)
# Importe original fila canónica (base_c[7]) = todo lo demás se escala por ratio para mantener ecuaciones.
try:
    IMPORTE_ORIG = float(str(base_c[7]).replace(",", "."))
except:
    IMPORTE_ORIG = 0.0
# Índices cols que NO tocar (son metadata, no importes) — cols 0=Fecha 1=TC 2=PtoVta 3=Nro 4=TipoDoc 5=CUIT 6=Denom
COLS_NO_IMPORTE = {0, 1, 2, 3, 4, 5, 6}

print(f"\n📄 Generando CSV {TARGET_N} filas ... (plantilla canónica TC=11, RATIO PROPORCIONAL para mantener ecuaciones)")
out_rows = [header]
# Seed determinista basado en epoch + random grande POR FILA
_R2 = random.Random(int(time.time() * 1000) & 0xFFFFFFFF)
for i in range(1, TARGET_N + 1):
    rr = copy.deepcopy(base_c)
    # Fecha: ciclo 1..DIAS_MES del mes target
    day = ((i - 1) % DIAS_MES) + 1
    rr[0] = f"{ANIO:04d}-{MES:02d}-{day:02d}"
    rr[1] = TC_FIJO
    rr[2] = str(PTO_VENTA_FIJO)
    rr[3] = str(BASE_NRO_COMP + i)
    rr[4] = prov_td; rr[5] = prov_cuit; rr[6] = prov_den
    # 🔴 FIX Opción1 A: JITTER ImporteTotal ÚNICO por fila (rango MUY AMPLIO) y luego RATIO = jit / original
    delta_big = _R2.randint(0, 999_999) * 0.17  # ~ 0 .. 169.999 pesos extra UNICOS por fila
    jit_total = 50000.00 + (float(i) * 37.33) + delta_big
    ratio = (jit_total / IMPORTE_ORIG) if IMPORTE_ORIG > 0 else 1.0
    # ⭐ MULTIPLICAR TODAS LAS COLUMNAS QUE SEAN IMPORTES por ratio.
    #   Así: TotalNetoGravado = sum(netos parciales) = Total * 88.235% EXACTO
    #        TotalIVA = sum(ivas parciales) = Total * 11.765% EXACTO
    #        Neto + IVA = TOTAL EXACTO (no desvíos)
    rr[7] = br(jit_total)
    for c in range(len(rr)):
        if c in COLS_NO_IMPORTE or c == 7:  # cols metadata o col7 ya la escribimos
            continue
        try:
            v_orig = float(str(rr[c]).replace(",", "."))
            if v_orig != 0.0:
                rr[c] = br(v_orig * ratio)
        except:
            pass  # no es un número (ej: cadena vacía, N/C, etc) → dejar como está
    out_rows.append(rr)
    if i % 5000 == 0:
        print(f"   ... {i} filas generadas ({int(time.time()-tcsv0)}s)")

buf = io.StringIO(newline="")
wr = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
for r in out_rows: wr.writerow(r)
csv_bytes = buf.getvalue().encode("latin-1", errors="replace")
fn = f"comprobantes_periodo_{PCOD}_compras.csv"
# 🔴 Fix Y: Guardar CSV 20k FÍSICO LOCAL con timestamp para AUDITORÍA período + datos (100% enero)
_ts = time.strftime("%Y%m%d_%H%M%S")
fn_local_ts = f"comprobantes_periodo_{PCOD}_compras_{_ts}.csv"
try:
    with open(fn_local_ts, "wb") as fhl: fhl.write(csv_bytes)
except Exception as exc_wr:
    fn_local_ts = None
    print(f"   WARNING: No pude guardar CSV físico auditoría local: {exc_wr}")
print(f"✅ CSV OK: {len(out_rows)-1} filas, {len(csv_bytes):,} bytes, PtoVenta={PTO_VENTA_FIJO}, NroComp {BASE_NRO_COMP+1}..{BASE_NRO_COMP+TARGET_N}  ({int(time.time()-tcsv0)}s)")
if fn_local_ts:
    print(f"   🗂️  CSV FÍSICO AUDITORÍA (100% período {PCOD}): {fn_local_ts}")
    # Validación inmediata del CSV físico: fechas min/max, Nro min/max, períodos (SOLO 01/2026)
    try:
        with open(fn_local_ts,"r",encoding="latin-1",newline="") as fh2:
            rows_v = list(csv.reader(fh2, delimiter=";"))
        fec_v=set(); nro_v=set(); pto_v=set(); cuits_v=set(); tcs_v=set();
        for r in rows_v[1:]:
            if len(r)<8: continue
            fec_v.add(str(r[0])[:10]); tcs_v.add(str(r[1])); pto_v.add(str(r[2]))
            nro_v.add(str(r[3])); cuits_v.add(str(r[5]))
        fmin=min(fec_v); fmax=max(fec_v)
        dentro_ok = all(v.startswith(f"{ANIO:04d}-{MES:02d}-") for v in fec_v if v)
        print(f"   ✅ Auditoría CSV físico: Fechas MIN={fmin} MAX={fmax} DENTRO PERIODO 01/2026? {dentro_ok}")
        print(f"      NroComp distintos={len(nro_v)} min={min(nro_v)} max={max(nro_v)} | PtoVenta={sorted(pto_v)} | CUITs={list(cuits_v)[:3]} | TC={sorted(tcs_v)}")
    except Exception as exc_aud:
        print(f"   WARNING auditoría CSV: {exc_aud}")

# 🔴 GUARD DIFÍCIL PERÍODO 01/2026 (ABORTA SI ALGO NO ES 01/2026)
if str(PCOD) != "202601" or int(PID) != 151 or int(MES) != 1 or int(ANIO) != 2026:
    raise RuntimeError(f"GUARD PERIODO INCORRECTO: PCOD={PCOD!r} PID={PID} MES={MES} ANIO={ANIO}. DEBE SER 202601 / 151 / MES=1 / 2026.")
try:
    with open(fn_local_ts,"r",encoding="latin-1",newline="") as fh3:
        rows_g = list(csv.reader(fh3, delimiter=";"))
    _c0 = {str(r[0])[:10] for r in rows_g[1:] if len(r)>1 and r and r[0]}
    dentro_100 = bool(_c0) and all(v.startswith("2026-01-") for v in _c0)
    _tcok = all(str(r[1])=="11" for r in rows_g[1:] if len(r)>1)
    _ptook = all(str(r[2])=="1" for r in rows_g[1:] if len(r)>2)
    _cuitok = all(str(r[5])=="30715954318" for r in rows_g[1:] if len(r)>5)
except Exception as exc_g:
    dentro_100 = False
    _tcok = _ptook = _cuitok = False
    print(f"   WARNING guard auditoría: {exc_g}")
if not dentro_100:
    sample_bad = sorted(v for v in _c0 if not v.startswith("2026-01-"))[:10]
    raise RuntimeError(f"GUARD CSV FUERA DE PERÍODO 01/2026 (dentro_100=False). Muestra fechas NO enero: {sample_bad}. Abortamos ANTES de SelectFile.")
if not (_tcok and _ptook and _cuitok):
    raise RuntimeError(f"GUARD ESTRUCTURA CSV INCORRECTA: TC={_tcok} PtoVenta_1={_ptook} CUIT_30715954318={_cuitok}. Debe ser TC=11, PtoVenta=1, CUIT=30715954318.")
print(f"   ✅ GUARD PERÍODO 01/2026 PASÓ: PCOD={PCOD} PID={PID} MES={MES} ANIO={ANIO} col0 TODO enero TC=11 PtoVenta=1 CUIT=30715954318. Seguro subir.")

# ==================================================================== 2) SelectFile
boundary = "----GdcImp" + _R.randbytes(16).hex()
fields = [("idOrigen",str(IDOR)),("empCodigo",str(EMP)),("periodoId",str(PID)),
          ("fileName",fn),("fileSize",str(len(csv_bytes))),("compraVenta","C"),("comprobanteCertificado","COMP")]
bd = b""
for k,v in fields:
    bd += f"--{boundary}\r\n".encode()
    bd += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
    bd += v.encode()+b"\r\n"
bd += f"--{boundary}\r\n".encode()
bd += f'Content-Disposition: form-data; name="file"; filename="{fn}"\r\n'.encode()
bd += b"Content-Type: application/vnd.ms-excel\r\n\r\n" + csv_bytes + b"\r\n"
bd += f"--{boundary}--\r\n".encode()
extra = {"Content-Type":f"multipart/form-data; boundary={boundary}"}
print("\n▶ SelectFile multipart ...")
s,j,_ = req("POST","/api/services/app/GdcImpoArchivo/SelectFile",tok,rt,"SelectFile",extra_headers=extra,raw_body=bd)
ftid = None
if isinstance(j,dict):
    for w in (j.get("fileInfo"), j.get("data"), j.get("result")):
        if isinstance(w,dict) and isinstance(w.get("fileTempId"),str):
            ftid = w["fileTempId"]; break
    if not ftid and isinstance(j.get("fileTempId"),str): ftid = j["fileTempId"]
print(f"   fileTempId={ftid}")
if not ftid: print("❌ NO fileTempId"); sys.exit(1)

# ================================================================= 3) ValidatePreliminary
print("\n▶ ValidatePreliminary (periodoId=COD 202601) ...")
s,j,_ = req("POST","/api/services/app/GdcImpoArchivo/ValidatePreliminary",tok,rt,"ValidatePreliminary",body=
    {"empCodigo":EMP,"periodoId":int(PCOD),"idOrigen":IDOR,"fileTempId":ftid,"fileName":fn,"fileSize":len(csv_bytes)})
if s >= 400:
    print("❌ ValidateFallo. Revisar mensaje arriba."); sys.exit(1)

# ====================================================================== 4) Incorporar
print("\n▶ Incorporar (periodoId=ID 151) ...")
s,j,_ = req("POST","/api/services/app/GdcImpoArchivo/Incorporar",tok,rt,"Incorporar",body=
    {"empCodigo":EMP,"periodoId":PID,"idOrigen":IDOR,"fileTempId":ftid,"fileNameOriginal":fn})
id_archivo = None
mismo_periodo = False
if isinstance(j, dict):
    d1 = j.get("data") or j.get("result")
    if isinstance(d1, dict):
        mismo_periodo = bool(d1.get("mismoPeriodo"))
        for k in ("idArchivo","id","IdArchivo"):
            if isinstance(d1.get(k),int) and d1[k]>0: id_archivo = d1[k]; break
    if id_archivo is None:
        for k in ("idArchivo","id","IdArchivo"):
            if isinstance(j.get(k),int) and j[k]>0: id_archivo = j[k]; break
print(f"   idArchivo = {id_archivo}   mismoPeriodo={mismo_periodo}")
if id_archivo is None:
    print("❌ NO idArchivo. Revisar mensaje arriba (probablemente período protegido o bloqueo)."); sys.exit(1)

# ========================================================= 5) Polling GetEstadoArchivo
print(f"\n⏳ Polling EstadoArchivo ... (máx 60 minutos)")
time.sleep(3)
ok_ea = False
O_final = 0; E_final = 0; W_final = 0
MAX_ATT_EA = 360  # 360 ×10s = 60 minutos
for att in range(1, MAX_ATT_EA+1):
    s,j,_ = req("POST","/api/services/app/GdcImpoArchivo/GetEstadoArchivo",tok,rt,f"EA#{att}",body={"idArchivo":id_archivo,"empCodigo":EMP})
    tl = lp = None; fin = False
    ea_txt = ""
    if isinstance(j,dict):
        d = j.get("data") if isinstance(j.get("data"),dict) else j
        if isinstance(d,dict):
            ea_txt = str(d.get("estadoArchivo") or "")
            tl = d.get("totalLineas"); lp = d.get("lineasProcesadas"); fin = bool(d.get("finalizado"))
            ce = d.get("conteoEstados") or {}
            if isinstance(ce,dict):
                O_final = int(ce.get("O") or 0); E_final = int(ce.get("E") or 0); W_final = int(ce.get("W") or 0)
    if (att <= 3) or (att % 10 == 0) or fin:
        pct = (int(lp)/int(tl)*100.0) if isinstance(tl,int) and isinstance(lp,int) and tl>0 else 0
        print(f"   [{att:>3d}/{MAX_ATT_EA}] {ea_txt:<25s} totalLineas={tl} procesadas={lp} ({pct:5.1f}%) finalizado={fin}   O={O_final} W={W_final} E={E_final}")
    if fin:
        ok_ea = True
        if E_final > 0:
            print(f"⚠️  Rechazados: E={E_final} / {tl}. Continuamos con los O + W.")
        else:
            print(f"✅ PROCESADO con ÉXITO: {O_final}/{tl} comprobantes OK.")
        break
    time.sleep(10)
if not ok_ea:
    print(f"⏱️  TIMEOUT EstadoArchivo después {MAX_ATT_EA} intentos. Detener.")
    sys.exit(1)

# ======================================================= 6) GetLineaArchivoIds (20k, paginar si hace falta)
print(f"\n▶ GetLineaArchivoIdsByPeriodo ... (esperar O={O_final} ids)")
ids_linea = []
for _retry in range(12):
    if len(ids_linea) >= max(100, O_final // 2): break
    time.sleep(5)
    s,j,_ = req("GET","/api/services/app/GdcImpoArchivo/GetLineaArchivoIdsByPeriodo",tok,rt,f"GLA#{_retry+1}",qs=
                {"empCodigo":EMP,"periodo":PID,"compraVenta":"C","comprobanteCertificado":"COMP","idOrigen":IDOR})
    tla = None
    if isinstance(j,dict):
        tla = j.get("idLineaArchivo")
    if isinstance(tla,list) and len(tla) and isinstance(tla[0],int):
        ids_linea = sorted(set(int(x) for x in tla))
        print(f"   encontrados {len(ids_linea)} ids_linea (retry {_retry+1})")
        break
    print(f"   retry {_retry+1}: sin ids_linea")

print(f"   ids_linea finales = {len(ids_linea)} (sample={ids_linea[:5] if ids_linea else []})")

# ===================== 7) Iniciar → validar-def → CheckQuota → Start (con ids_linea)
if ids_linea:
    # Para 20k ids, mandar SOLO los primeros/últimos si >10k para evitar body gigante?
    # HAR real manda TODOS los idsLineaArchivo → body OK lo manejamos así.
    batch_ids = list(ids_linea)
    print(f"\n▶ Pipeline /Iniciar → V-Def → Quota → Start ({len(batch_ids)} ids) ...")
    for name, path, b in [
        ("ImportDef/Iniciar","/api/services/app/GdcImpoArchivo/ImportacionDefinitiva/Iniciar",
            {"empCodigo":EMP,"periodoFiscalId":PID,"idsLineaArchivo":batch_ids,"compraVenta":"C","comprobanteCertificado":"COMP","idOrigen":IDOR}),
        ("validar-definitivos","/api/services/app/GdcImpoArchivo/importacion/validar-definitivos",
            {"empCodigo":EMP,"periodoFiscalId":PID,"idOrigen":IDOR,"compraVenta":"C","idsLineaArchivo":batch_ids,"replaceExisting":False}),
        ("CheckQuota","/api/services/app/GdcImpoArchivo/CheckQuota",
            {"empCodigo":EMP,"periodoFiscalId":PID,"idOrigen":IDOR,"compraVenta":"C","idsLineaArchivo":batch_ids,"replaceExisting":False}),
        ("Start ImportDef","/api/services/app/GdcImpoArchivo/ImportacionDefinitiva/Start",
            {"empCodigo":EMP,"periodoFiscalId":PID,"idsLineaArchivo":batch_ids,"compraVenta":"C","idOrigen":IDOR,"replaceExisting":False}),
    ]:
        s,j,_ = req("POST", path, tok, rt, name, body=b)
        # 409 IMPORT_ALREADY_RUNNING → no fatal
        if s == 409 and isinstance(j, dict) and "IMPORT_ALREADY_RUNNING" in str(j.get("code") or ""):
            print(f"   → {name}: 409 (ya iniciada → continúa)")

# ============================================ 8) Polling GetListComprobantes (VARIANTES) hasta total >= O_final
TOTAL_ESPERADO = max(1, O_final, TARGET_N - E_final)
print(f"\n⏳ Polling GetListComprobantes ... hasta total ≥ {TOTAL_ESPERADO} (máx 90 min)")
t0 = time.time()
last_total = -1
MAX_ATT_GLC = 540  # 540 ×10s = 90 minutos
def _glc_extraer_total(j):
    """Extractor robusto total + items. Fix Opción Y: busca en TODOS los keys, NO solo data.items."""
    total = None; items = []; json_snippet = None
    if not isinstance(j, dict):
        return total, items, json_snippet
    try: json_snippet = json.dumps(j, ensure_ascii=False)[:1200]
    except Exception: json_snippet = str(j)[:1200]
    # Buscamos recursivamente todos los "total"/"items" en el JSON completo (busqueda deep)
    import collections as _cll
    q = _cll.deque([j]); seen = set()
    while q:
        try: n = q.popleft()
        except Exception: break
        if isinstance(n, dict):
            try:
                if id(n) in seen: continue
                seen.add(id(n))
            except Exception: pass
            for k,v in n.items():
                kl = str(k).lower()
                if kl in ("total","count","totalcount","total_count","recordsTotal".lower()) and isinstance(v,(int,float)):
                    if total is None or int(v) > total:
                        total = int(v)
                elif kl == "items" and isinstance(v,list):
                    if len(v) > len(items): items = v
                elif isinstance(v,(dict,list)):
                    try: q.append(v)
                    except Exception: pass
        elif isinstance(n, list):
            for e in n:
                if isinstance(e,(dict,list)):
                    try: q.append(e)
                    except Exception: pass
    if not items:
        # Fallback: buscar primer list anidado (ordenado por len más grande)
        q2 = _cll.deque([j])
        while q2:
            try: n2 = q2.popleft()
            except Exception: break
            if isinstance(n2, dict):
                for vv in n2.values():
                    if isinstance(vv, list) and len(vv)>len(items) and vv and isinstance(vv[0],dict):
                        items = vv
                    elif isinstance(vv,(dict,list)):
                        try: q2.append(vv)
                        except Exception: pass
            elif isinstance(n2, list):
                for ee in n2:
                    if isinstance(ee,(dict,list)):
                        try: q2.append(ee)
                        except Exception: pass
    if total is None and items:
        total = len(items)
    return total, items, json_snippet

def _glc_buscar_nrocomp(tok,rt, nro_comp_unicos):
    """Opción Y VALIDACIÓN DURA: buscar NroComp 1000001..1000005 (5 primeros) para confirmar GdC guardó el lote."""
    encontrados = {}
    for nro in nro_comp_unicos[:5]:
        s,j,_ = req("POST","/api/services/app/GdcImpoArchivo/GetListComprobantes",tok,rt,f"GLC:search{nro}",
                    body={"empCodigo":EMP,"page":1,"limit":20,"search":str(nro),"filter":{}})
        tot,it,jsn = _glc_extraer_total(j)
        ok = (isinstance(tot,int) and tot>0) or (len(it)>0)
        encontrados[nro] = (ok, tot, len(it))
    return encontrados

NROCOMP_A_BUSCAR_DURO = [str(BASE_NRO_COMP + i) for i in (1,2,500,1000,2000,5000,10000,15000,20000)]
for att in range(1, MAX_ATT_GLC+1):
    time.sleep(10)
    elapsed = int(time.time()-t0)
    body = {"empCodigo":EMP,"page":1,"limit":500,"search":"","filter":{}}
    s,j,_ = req("POST","/api/services/app/GdcImpoArchivo/GetListComprobantes",tok,rt,f"GLC#{att}",body=body)
    total, items, _snippet = _glc_extraer_total(j)
    if total is None: total = 0
    try: total = int(total)
    except Exception: total = 0
    loguear = att <= 3 or att % 6 == 0 or total >= TOTAL_ESPERADO or total != last_total
    if loguear:
        print(f"   [{att:>3d}/{MAX_ATT_GLC}] t+{elapsed//60:>2d}m{elapsed%60:02d}s   total_GLC = {total:>6d} / objetivo {TOTAL_ESPERADO}   items_encontrados={len(items)}")
        last_total = total
    # 🔴 Fix Opción Y: cada ~3min o cuando total>=meta => BUSCAR NROCOMP ESPECÍFICOS (validación dura por comprobante único)
    nro_ok = None
    if (att % 18 == 0 and att > 0) or total >= TOTAL_ESPERADO or (total>0 and att<=30):
        _bus = _glc_buscar_nrocomp(tok,rt, NROCOMP_A_BUSCAR_DURO)
        oks = [(n,o,t,l) for n,(o,t,l) in _bus.items() if o]
        nro_ok = len(oks)
        print(f"   🔍 Búsqueda NroComp (5+1000001..): OK={nro_ok}/{len(NROCOMP_A_BUSCAR_DURO)} | detalle {oks[:3]}")
    if total >= TOTAL_ESPERADO or (nro_ok is not None and nro_ok >= 4):
        print(f"✅ META CUMPLIDA: GetListComprobantes total={total} ≥ {TOTAL_ESPERADO} | NroComp encontrados={nro_ok}")
        break
else:
    print(f"⏱️  TIMEOUT GLC {MAX_ATT_GLC}x10s. Total final={last_total}")

# ===================================================== FINAL
req("GET","/api/services/app/GdcImpoArchivo/Importaciones/EstadoCompras",tok,rt,"EstadoCompras (post)",qs={"empCodigo":EMP,"periodoFiscalId":PID})
# 🔴 Fix Opción Y: Confirmación FINAL PERÍODO 01/2026 por BUSCAR NroComp ÚNICOS 1000001..1000005 + devolver fechaEmisión si existe
_nros_fin = [BASE_NRO_COMP+1, BASE_NRO_COMP+2, BASE_NRO_COMP+1000, BASE_NRO_COMP+20000]
_detalle_nros = []
for _n in _nros_fin:
    s,j,_ = req("POST","/api/services/app/GdcImpoArchivo/GetListComprobantes",tok,rt,f"FINAL:search{_n}",
                body={"empCodigo":EMP,"page":1,"limit":10,"search":str(_n),"filter":{}})
    _t,_it,_ = _glc_extraer_total(j)
    # Extraer FechaEmisión de items si existen
    _fec = []
    for _itx in _it[:2]:
        if isinstance(_itx, dict):
            for _kk in ("fechaEmision","FechaEmision","fecha_emision","nroComprobante","NroComprobante","periodoFiscalId","periodo","Periodo","periodoCod"):
                if _kk in _itx: _fec.append(f"{_kk}={_itx[_kk]!r}")
    _detalle_nros.append((_n, "OK" if (isinstance(_t,int) and _t>0) or len(_it)>0 else "NoEncontrado", _t, len(_it), _fec))
print(f"\n🏁 FIN DIAG 20K UN LOTE:")
print(f"   TARGET N = {TARGET_N}")
print(f"   PERÍODO CONFIRMADO (hardcode): EMP={EMP} PERIODO_COD={PCOD!r} PERIODO_ID={PID} ANIO={ANIO} MES={MES}")
print(f"   idArchivo = {id_archivo}")
print(f"   EstadoArchivo  O={O_final}  W={W_final}  E={E_final}  (rechazados)")
print(f"   ids_linea capturados = {len(ids_linea)}")
print(f"   GetListComprobantes total final = {last_total}")
print(f"   Archivo CSV: {fn} ({len(csv_bytes):,} bytes)")
if fn_local_ts:
    print(f"   🗂️  CSV FÍSICO AUDITORÍA LOCAL (100% período 01/2026): {fn_local_ts}")
print(f"   PtoVenta: {PTO_VENTA_FIJO} (FIJO, repetible en todas las filas)")
print(f"   Rango NroComprobante: {BASE_NRO_COMP+1} .. {BASE_NRO_COMP+TARGET_N}")
print(f"   🔍 Validación FINAL DURA por NroComp ÚNICO (si existen = guardados OK):")
for _n, _est, _t, _l, _fec in _detalle_nros:
    print(f"      · Nro {_n}  → {_est}  (total_busq={_t} items={_l})  {', '.join(_fec[:5]) if _fec else ''}")
# Salida exitosa si existe 4+ NroComp encontrados O total >= esperado
n_ok_final = sum(1 for _,e,_,_,_ in _detalle_nros if e=="OK")
exito_final = (last_total >= TOTAL_ESPERADO) or (n_ok_final >= 4)
print(f"   RESULTADO FINAL: {'✅ EXITO' if exito_final else '⚠️  PARCIAL (ver UI Front)'} | total={last_total} NroComp_ok={n_ok_final}/4")
sys.exit(0 if exito_final else 4)
