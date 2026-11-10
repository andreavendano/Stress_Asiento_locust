# =============================================================================
# scripts/blazemeter_json_to_locust.py  —  ADAPTADOR BLAZEMETER JSON -> LOCUST
# =============================================================================
# Formato de entrada:  JSON exportado por la extensión Blazemeter de Chrome
#                      (array "traffic" con "method", "url", "headers"[{name,value}],
#                      "body" = LISTA con 1 string JSON, etc.)
#
# Uso:
#   python scripts/blazemeter_json_to_locust.py ^
#       har_input\gdccomprobantesnuevo-blazemeter.json ^
#       -o locustfile.py
# =============================================================================
import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


_HEADERS_OMITIR = {
    "host", "content-length", "connection", "accept-encoding",
    "user-agent", "cookie", ":authority", ":method", ":path",
    ":scheme", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
    "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "sec-fetch-user",
    "upgrade-insecure-requests", "0",
}


def _parse_body(item: Dict[str, Any]) -> Tuple[Optional[str], Optional[Any]]:
    """
    Blazemeter guarda el body como LISTA con 1 solo string JSON.
    Devuelve:
        (tipo: "json" | "data" | None, valor)
        - Si "json": valor = OBJETO Python parseado (dict/list). Luego usaremos repr()
          al imprimirlo para generar sintaxis Python valida (True/False/None en vez de
          true/false/null).
        - Si "data": valor = string crudo (form-urlencoded, multipart, etc.)
    """
    raw_body = item.get("body") or []
    if not raw_body:
        return None, None
    primer = raw_body[0] if isinstance(raw_body, list) else raw_body
    if not isinstance(primer, str):
        return None, None
    primer = primer.strip()
    if not primer:
        return None, None
    # Intentar JSON
    if primer.startswith("{") or primer.startswith("["):
        try:
            parsed = json.loads(primer)
            return "json", parsed
        except json.JSONDecodeError:
            pass
    return "data", primer


def _extraer_headers(item: Dict[str, Any]) -> Dict[str, str]:
    raw = item.get("headers") or []
    out: Dict[str, str] = {}
    for h in raw:
        nombre = str(h.get("name", "")).lower()
        if nombre in _HEADERS_OMITIR:
            continue
        out[h.get("name", "")] = str(h.get("value", ""))
    return out


def _tiene_authorization_bearer(headers: Dict[str, str]) -> bool:
    for k, v in headers.items():
        if k.lower() == "authorization" and isinstance(v, str) and v.lower().startswith("bearer "):
            return True
    return False


def _extraer_body_login_authenticate(body_parsed: Any) -> Optional[Dict[str, Any]]:
    """
    Si body_parsed (resultado de _parse_body, ya parseado a objeto Python)
    parece el login Authenticate -> devuelve el dict.
    """
    if not isinstance(body_parsed, dict):
        return None
    if "userNameOrEmailAddress" in body_parsed or "password" in body_parsed:
        return body_parsed
    return None


def _to_url_relativa(raw: str) -> str:
    u = urlparse(raw)
    qs = f"?{u.query}" if u.query else ""
    path = u.path
    # Algunas URLs de Blazemeter traen "//api/..." (doble barra tras dominio). Arreglar.
    path = re.sub(r"^/+", "/", path)
    return f"{path}{qs}"


def _nombre_stat(url_relativa: str) -> str:
    """Agrupa estadísticas sin query string."""
    return url_relativa.split("?")[0] or "/"


def convertir(
    ruta_json: str,
    *,
    saltar_options_cors: bool = True,
    saltar_estaticos: bool = True,
) -> Tuple[str, Dict[str, Any]]:

    with open(ruta_json, "r", encoding="utf-8") as f:
        bm = json.load(f)

    nombre_test = bm.get("name") or "blazemeter_test"
    traffic = bm.get("traffic") or []
    if not traffic:
        raise SystemExit("ERROR: el JSON de Blazemeter no tiene array 'traffic'")

    # --- Detectar host API y host app ---------------------------------------
    hosts = set()
    for t in traffic:
        pu = urlparse(t.get("url") or "")
        if pu.netloc:
            hosts.add(f"{pu.scheme}://{pu.netloc}")
    host_api = None
    host_app = None
    for h in sorted(hosts):
        if ("host-qa" in h.lower()) or ("host" in h.lower()):
            host_api = h
            break
    if not host_api:
        host_api = sorted(hosts)[0]
    for h in sorted(hosts):
        if h != host_api:
            host_app = h
            break

    # --- Filtrar entradas válidas -------------------------------------------
    filt: List[Dict[str, Any]] = []
    for t in traffic:
        method = (t.get("method") or "GET").upper()
        url = t.get("url") or ""
        if not url:
            continue
        if saltar_options_cors and method == "OPTIONS":
            continue
        if saltar_estaticos:
            path = urlparse(url).path.lower()
            if any(path.endswith(e) for e in (
                ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                ".woff", ".woff2", ".ttf", ".mp4", ".map", ".webp",
            )):
                continue
        filt.append(t)

    # --- Detectar login / credentials ----------------------------------------
    credenciales: Optional[Dict[str, Any]] = None
    abp_tenant_id: Optional[str] = None
    login_url_rel: Optional[str] = None

    for t in filt:
        method = (t.get("method") or "GET").upper()
        url = t.get("url") or ""
        if "/api/tokenauth/authenticate" in url.lower() and method == "POST":
            _, body_value = _parse_body(t)
            credenciales = _extraer_body_login_authenticate(body_value)
            login_url_rel = _to_url_relativa(url)
        # Abp.TenantId de cualquier header
        for h in (t.get("headers") or []):
            if str(h.get("name", "")).lower() == "abp.tenantid":
                abp_tenant_id = str(h.get("value", ""))
        # Buscamos Authorization Bearer para NO repetirlo por request
        if abp_tenant_id and credenciales and login_url_rel:
            break

    # --- Construir calls de requests (flujo ordenado) -----------------------
    calls: List[str] = []
    total_autenticados = 0
    total_con_body = 0
    total_salteados_login_duplicado = 0
    total_cross_host = 0
    usa_authenticate = bool(credenciales and login_url_rel)
    host_api_netloc = urlparse(host_api).netloc.lower()

    contador_pasos_efectivos = 0

    for t in filt:
        method = (t.get("method") or "GET").upper()
        url = t.get("url") or ""
        url_rel = _to_url_relativa(url)
        stat = _nombre_stat(url_rel)
        headers = _extraer_headers(t)
        necesita_auth = _tiene_authorization_bearer(headers)
        headers_limpio = {k: v for k, v in headers.items() if k.lower() not in {"authorization", "abp.tenantid"}}
        body_kind, body_value = _parse_body(t)

        # Punto 1: Si se usa on_start (login Authenticate) y la petición actual
        # es precisamente un POST a Authenticate => SALTARLA del flujo grabado.
        if usa_authenticate and method == "POST" and "/api/tokenauth/authenticate" in url.lower():
            total_salteados_login_duplicado += 1
            continue

        # Punto 2: Si esta petición va a OTRO host (APP, etc.), enviar URL
        # absoluta para que Locust no la mande al host API.
        parsed_url = urlparse(url)
        cross_host = parsed_url.netloc.lower() != host_api_netloc
        if cross_host:
            total_cross_host += 1

        contador_pasos_efectivos += 1
        idx = contador_pasos_efectivos

        lineas: List[str] = []
        lineas.append(f"        # --- Paso {idx}: {method} {url[:160]}")
        if cross_host:
            lineas.append(f"        # (host distinto al API: {parsed_url.scheme}://{parsed_url.netloc})")

        extra = [f'name={stat!r}']

        headers_final: Dict[str, str] = {}
        if abp_tenant_id:
            headers_final["Abp.TenantId"] = abp_tenant_id
        headers_final.update(headers_limpio)

        if necesita_auth and usa_authenticate:
            total_autenticados += 1
        if headers_final:
            extra.append(f"headers={json.dumps(headers_final, ensure_ascii=False)}")
        if body_kind and body_value is not None:
            total_con_body += 1
            if body_kind == "json":
                # IMPORTANTE: repr() para que el objeto Python salga con booleans
                # True/False y None correctos. NO usar json.dumps aquí (genera
                # true/false/null que Python no reconoce como sintaxis).
                extra.append(f"json={body_value!r}")
            else:
                extra.append(f"data={body_value!r}")

        if necesita_auth and usa_authenticate:
            lineas.append("        self.client.headers['Authorization'] = 'Bearer ' + self.access_token")

        kwargs = ", ".join(extra)
        method_r = repr(method)
        # Elegir: URL relativa (si mismo host) o ABSOLUTA (si host distinto)
        url_a_usar = url if cross_host else url_rel
        url_r = repr(url_a_usar)
        lineas.append(f"        self.client.request({method_r}, {url_r}, {kwargs})")

        calls.append("\n".join(lineas))

    task_body = "\n\n".join(calls) if calls else "        pass"

    # --- Bloque de seguridad / credenciales ----------------------------------
    seguridad_bloque = ""
    if credenciales or abp_tenant_id:
        seguridad_bloque = "\n# ====== IMPORTANTE DE SEGURIDAD ======\n"
        seguridad_bloque += "# Credenciales y tenant detectadas en la grabación de Blazemeter.\n"
        seguridad_bloque += "# Para entornos reales: SACA estos valores a variables de entorno (.env)\n"
        seguridad_bloque += "# y NO los dejes hardcodeados. Ejemplo:\n"
        seguridad_bloque += "#   import os; from dotenv import load_dotenv; load_dotenv()\n"
        seguridad_bloque += "#   USER = os.environ['LOADTEST_USER']; PASS = os.environ['LOADTEST_PASS']\n"
        seguridad_bloque += "# ======================================\n"
        if abp_tenant_id:
            seguridad_bloque += f"ABP_TENANT_ID = {abp_tenant_id!r}  # TODO: mover a .env si cambia por entorno\n"
        if credenciales:
            # Importante: usar repr() para que el dict salga con sintaxis Python valida
            # (False/None mayuscula). Si usamos json.dumps() salen false/null (sintaxis JS).
            seguridad_bloque += (
                f"LOGIN_URL = {login_url_rel!r}\n"
                f"LOGIN_PAYLOAD = {credenciales!r}  # TODO: leer USER/PASS de .env\n"
            )

    # --- Ensamblar locustfile.py --------------------------------------------
    on_start_bloque = ""
    if usa_authenticate:
        on_start_bloque = """
    def on_start(self):
        # Paso unico por usuario virtual: hace login y guarda el Bearer token.
        payload = dict(LOGIN_PAYLOAD)
        payload["userNameOrEmailAddress"] = payload.get("userNameOrEmailAddress")
        payload["password"] = payload.get("password")

        headers = {"Content-Type": "application/json-patch+json", "Abp.TenantId": ABP_TENANT_ID}
        with self.client.post(
            LOGIN_URL,
            json=payload,
            headers=headers,
            name="/api/TokenAuth/Authenticate (login)",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                mensaje = "Login fallo: HTTP " + str(resp.status_code)
                resp.failure(mensaje)
                return
            data = resp.json()
            # Estructura ABP habitual = data.result.accessToken o data.accessToken
            token = None
            if isinstance(data, dict):
                r = data.get("result")
                if isinstance(r, dict):
                    token = r.get("accessToken")
                if not token:
                    token = data.get("accessToken")
            if not token:
                resp.failure("Respuesta de login sin accessToken")
                return
            self.access_token = token
            resp.success()
"""

    template = f'''"""
locustfile.py — generado AUTOMÁTICAMENTE desde Blazemeter JSON.
Fuente       : {os.path.basename(ruta_json)}
Test name    : {nombre_test}
Fecha / Hora : {__import__("datetime").datetime.now().isoformat(timespec="seconds")}
Host API     : {host_api!r}
Host app     : {host_app!r}
Tenant ABP   : {abp_tenant_id!r}
Peticiones   : {len(traffic)} totales en Blazemeter, {len(calls)} en locustfile (efectivas)
  - Autenticadas (Bearer) : {total_autenticados}
  - Con body JSON/form    : {total_con_body}
  - OPTIONS CORS omitidas : {"SÍ" if saltar_options_cors else "NO"}
  - Login duplicado saltado: {total_salteados_login_duplicado}
  - Peticiones cross-host : {total_cross_host}
"""
# =============================================================================
# ====== IMPORTANTE DE SEGURIDAD ==============================================
# Credenciales y tenant detectadas en la grabación de Blazemeter.
# Para entornos reales: SACA estos valores a variables de entorno (.env)
# y NO los dejes hardcodeados. Ejemplo:
#   import os
#   from dotenv import load_dotenv
#   load_dotenv()
#   USER = os.environ["LOADTEST_USER"]
#   PASS = os.environ["LOADTEST_PASS"]
#   ABP_TENANT_ID = os.environ["LOADTEST_ABP_TENANT_ID"]
# =============================================================================
{seguridad_bloque}

from locust import HttpUser, TaskSet, between, task


class FlujoGdCComprobantes(TaskSet):
{on_start_bloque}
    @task
    def flujo_completo_grabado(self):
{task_body}


class GdCComprobantesUser(HttpUser):
    wait_time = between(1, 3)
    host = {host_api!r}
    tasks = {{FlujoGdCComprobantes}}
'''

    meta = {
        "host_api": host_api,
        "host_app": host_app,
        "abp_tenant_id": abp_tenant_id,
        "total_bm": len(traffic),
        "mapeadas": len(calls),
        "autenticadas": total_autenticados,
        "con_body": total_con_body,
        "credenciales_detectadas": bool(credenciales),
        "login_saltado": total_salteados_login_duplicado,
        "cross_host": total_cross_host,
    }
    return template, meta


def main() -> None:
    p = argparse.ArgumentParser(description="Convierte Blazemeter JSON (traffic[]) a locustfile.py")
    p.add_argument("json_file", help="Ruta al JSON exportado por Blazemeter")
    p.add_argument("-o", "--output", default="locustfile.py", help="locustfile.py de salida")
    p.add_argument("--no-skip-options", action="store_true", help="NO omitir peticiones OPTIONS CORS preflight")
    p.add_argument("--include-static", action="store_true", help="Incluir .css/.js/.png etc.")
    args = p.parse_args()

    if not os.path.exists(args.json_file):
        raise SystemExit(f"ERROR: archivo no encontrado: {args.json_file}")

    codigo, meta = convertir(
        args.json_file,
        saltar_options_cors=not args.no_skip_options,
        saltar_estaticos=not args.include_static,
    )
    Path(args.output).write_text(codigo, encoding="utf-8")
    print(f"[OK] Generado : {Path(args.output).resolve()}")
    print(f"     Test name: {os.path.basename(args.json_file)}")
    print(f"     Host API : {meta['host_api']}")
    print(f"     Host app : {meta['host_app']}")
    print(f"     Tenant   : {meta['abp_tenant_id']}")
    print(f"     Peticiones en Blazemeter: {meta['total_bm']}")
    print(f"     Efectivas en locustfile : {meta['mapeadas']}")
    print(f"        - Bearer auth        : {meta['autenticadas']}")
    print(f"        - Con body           : {meta['con_body']}")
    print(f"        - Login duplicado skip: {meta['login_saltado']}")
    print(f"        - Cross-host (URL abs): {meta['cross_host']}")
    print(f"     Credenciales login detectadas: {'SÍ (ver bloque SEGURIDAD arriba)' if meta['credenciales_detectadas'] else 'NO'}")


if __name__ == "__main__":
    main()
