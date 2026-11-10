# =============================================================================
# scripts/har_to_locust.py  —  CONVERTIDOR DE HAR A LOCUSTFILE (Patrón FACADE)
# =============================================================================
# Patrón de diseño aplicado: FACADE (Fachada)
#   - El usuario solo interactúa con 1 cosa: convert_har() o el CLI de abajo.
#   - Internamente, la fachada hace TODO el trabajo difícil: parsear el JSON del
#     HAR, detectar host, filtrar recursos estáticos, extraer body/form/json,
#     limpiar headers, generar el código Python y escribir el locustfile.
#   - El consumidor (tú) NO necesita saber NADA de cómo se hace por dentro.
#
# Qué es un HAR (HTTP Archive):
#   Formato JSON estándar que graba TODAS las peticiones HTTP de una sesión de
#   navegador. Lo generan Blazemeter, Chrome DevTools, Firefox, Postman, etc.
#
# Uso básico por CLI:
#   python scripts/har_to_locust.py har_input/mi_grabacion.har -o locustfile.py
#
# Banderas opcionales:
#   --include-static     No omitir .css/.js/.png (por defecto SÍ se omiten)
#   --include-errors     No omitir respuestas 4xx/5xx (por defecto SÍ se omiten)
#   --base-url URL       Forzar host distinto al detectado en la 1ª petición
# =============================================================================

# --- Librerías estándar usadas (sin dependencias externas, solo Python core) --
import argparse  # Parser de argumentos por CLI (--flag, posicionales, etc.)
import json      # Serializador/deserializador JSON
import os        # Interactuar con rutas del S.O. y variables de entorno
import re        # Expresiones regulares (limpiar nombres)
from pathlib import Path  # API moderna para archivos (más segura que os.path)
from typing import Any, Dict, List, Optional, Tuple  # Tipos estáticos (type hints)
from urllib.parse import urlparse  # Trocear URLs: scheme, netloc, path, query


# =============================================================================
# PASO 0 — CONSTANTES INTERNAS (no tocar salvo que sea necesario)
# =============================================================================
# Extensiones de archivos estáticos. Las filtramos POR DEFECTO porque rara vez
# aportan valor en una prueba de estrés de negocio, y ensucian los reportes.
_STATIC_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".map", ".mp4", ".mp3", ".webp",
}


# =============================================================================
# PASO 1 — FUNCIONES AUXILIARES (helpers) privadas (empiezan por _)
# =============================================================================
# Cada una hace 1 sola cosa (Single Responsibility). La fachada las compone.

def _is_static(url: str) -> bool:
    """Devuelve True si la URL termina en una extensión de archivo estático."""
    # Extrae solo el "path" de la URL (lo que va después del dominio), minúsculas
    path = urlparse(url).path.lower()
    # "any" = al menos 1 coincidencia con la lista _STATIC_EXTENSIONS
    return any(path.endswith(ext) for ext in _STATIC_EXTENSIONS)


def _sanitize_name(method: str, url: str) -> str:
    """
    Crea un nombre seguro (válido para Python) a partir de método + URL.
    Evita caracteres raros: barras, guiones, espacios.
    Ejemplo: GET /api/v1/users/123  ->  get_api_v1_users_123
    """
    parsed = urlparse(url)
    # strip("/") quita barras al principio/final. Si queda vacío -> "root"
    path = parsed.path.strip("/") or "root"
    # Reemplaza TODO lo que NO sea letra/número por "_"
    path = re.sub(r"[^A-Za-z0-9]+", "_", path)
    # Colapsa varios __ seguidos en uno solo y limpia sobrantes
    path = re.sub(r"_+", "_", path).strip("_")
    return f"{method.lower()}_{path or 'index'}"


def _extract_body(entry: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrae el cuerpo (body) de una petición HAR POST/PUT/PATCH.
    Devuelve TUPLA:
      (tipo: "json" | "data" | None,  valor_raw: str | None)
    - json  : usar json=...  en requests
    - data  : usar data=...  en requests (form-urlencoded o texto plano)
    """
    # "entry" = 1 elemento del array log.entries[] del HAR
    req = entry.get("request", {})
    post_data = req.get("postData")  # campo estándar HAR para el body
    if not post_data:
        return None, None  # GET/DELETE sin body -> nada que enviar

    mime = (post_data.get("mimeType") or "").lower()  # ej: "application/json"
    text = post_data.get("text")    # body como string (JSON, XML, texto)
    params = post_data.get("params")  # body tipo form-urlencoded (clave/valor)

    # Caso A: hay texto plano/JSON (el más común en APIs modernas)
    if text:
        if "x-www-form-urlencoded" in mime:
            return "data", text  # formulario clásico (key=val&key2=val2)
        return "json", text     # JSON API REST/GraphQL

    # Caso B: hay params (formulario multipart/form-data o form clásico)
    if params:
        body_pairs = []
        for p in params:
            k = p.get("name", "")
            v = p.get("value", "")
            body_pairs.append(f"{k}={v}")
        return "data", "&".join(body_pairs)

    return None, None


def _extract_headers(entry: Dict[str, Any]) -> Dict[str, str]:
    """
    Extrae los headers RELEVANTES de la petición HAR.
    Omite headers que Locust calcula automáticamente (Host, Content-Length,
    cookies, UA, etc.) para evitar duplicados y fallos.
    """
    req = entry.get("request", {})
    headers_list = req.get("headers", [])  # en HAR los headers son un array [{name,value}]

    # Set de headers que NUNCA enviamos (pisan el valor correcto de Locust)
    skip = {
        "host", "content-length", "connection", "accept-encoding",
        "user-agent", "cookie", ":authority", ":method", ":path",
        ":scheme", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
    }
    out = {}
    for h in headers_list:
        name = str(h.get("name", "")).lower()
        if name in skip:
            continue
        out[h.get("name", "")] = str(h.get("value", ""))
    return out


def _extract_cookies(entry: Dict[str, Any]) -> Dict[str, str]:
    """
    Extrae las cookies de la petición HAR. Se usan solo con fines informativos
    (se muestran en la metada del convertidor); Locust gestiona la sesión por
    ti automáticamente usando self.client (es una requests.Session).
    """
    req = entry.get("request", {})
    cookies = req.get("cookies", [])
    out = {}
    for c in cookies:
        out[c.get("name", "")] = c.get("value", "")
    return out


def _is_absolute(url: str) -> bool:
    """Devuelve True si la URL tiene dominio (ej: https://a.com/x) y no es /x"""
    return bool(urlparse(url).netloc)


# =============================================================================
# PASO 2 — FUNCIÓN FACHADA PÚBLICA  (lo que usaría un programador que importa)
# =============================================================================
def convert_har(
    har_path: str,
    *,  # a partir de aquí TODO debe nombrarse al invocar (keyword-only args)
    base_url: Optional[str] = None,
    skip_static: bool = True,
    skip_errors: bool = True,
) -> Tuple[str, Dict[str, str]]:
    """
    FACADE PRINCIPAL:
      Entrada  : Ruta a un archivo HAR + flags opcionales
      Salida   : Tupla (codigo_locustfile_generado_como_string, diccionario_metadata)

    Pasos internos:
      1. Leer y parsear el JSON del HAR.
      2. Detectar o usar la URL base forzada.
      3. Filtrar las entradas (quitar estáticas, quitar errores si pide).
      4. Iterar las entradas y generar una línea self.client.request(...) c/u.
      5. Ensamblar todo en una plantilla de clase Locust válida (HttpUser + TaskSet).
    """

    # -------- SUBPASO 2.1: leer el HAR desde disco --------------------------
    with open(har_path, "r", encoding="utf-8") as f:
        har = json.load(f)  # convierte texto JSON -> dict/list de Python

    # -------- SUBPASO 2.2: extraer el array log.entries[] (estándar HAR) -----
    entries = har.get("log", {}).get("entries", [])
    if not entries:
        raise ValueError("HAR sin entradas (log.entries vacío)")

    # -------- SUBPASO 2.3: detectar URL base (host del target) --------------
    if base_url is None:
        # Cogemos la 1ª petición y sacamos scheme + dominio
        first_url = entries[0].get("request", {}).get("url", "")
        p = urlparse(first_url)
        if p.scheme and p.netloc:
            # p.scheme = "https"; p.netloc = "api.ejemplo.com"
            base_url = f"{p.scheme}://{p.netloc}"
        else:
            # Caso HAR incompleto -> valor de seguridad
            base_url = "https://ejemplo.api.com"

    # -------- SUBPASO 2.4: filtrar entradas relevantes ----------------------
    filtered_entries: List[Dict[str, Any]] = []
    for e in entries:
        req = e.get("request", {})
        resp = e.get("response", {})
        url = req.get("url", "")
        if not url:
            continue  # entry rota — sin URL
        if skip_static and _is_static(url):
            continue  # saltarse recursos estáticos
        status = int(resp.get("status", 0) or 0)
        if skip_errors and status >= 400:
            continue  # saltarse respuestas de error (ruido)
        filtered_entries.append(e)

    # -------- SUBPASO 2.5: generar las líneas de código Locust --------------
    task_calls: List[str] = []          # cada elemento = 1 petición traducida
    unique_names = set()                # evitar nombres duplicados (colisiones)
    sample_cookies: Dict[str, str] = {}  # colección de cookies para el reporte

    # enumerate con start=1 => los pasos salen 1, 2, 3, ... (human-readable)
    for idx, e in enumerate(filtered_entries, start=1):
        req = e.get("request", {})
        method = (req.get("method") or "GET").upper()  # GET / POST / PUT...
        raw_url = req.get("url", "")

        # Convertir URL absoluta a relativa (el host lo pone HttpUser.host)
        if _is_absolute(raw_url):
            p = urlparse(raw_url)
            call_url = p.path + (f"?{p.query}" if p.query else "")
        else:
            call_url = raw_url
        if not call_url.startswith("/"):
            call_url = "/" + call_url

        # Generar nombre único
        name = _sanitize_name(method, raw_url)
        if name in unique_names:
            name = f"{name}_{idx}"
        unique_names.add(name)

        # Extraer piezas de la petición
        code_lines: List[str] = []
        code_lines.append(f"        # PASO {idx}: {method} {raw_url[:140]}")
        headers = _extract_headers(e)
        cookies = _extract_cookies(e)
        sample_cookies.update(cookies)
        body_kind, body_value = _extract_body(e)

        # Construir kwargs de self.client.request(method, url, ...)
        extra_kwargs: List[str] = []
        # El parámetro "name" agrupa métricas en reportes (MUY importante)
        extra_kwargs.append(f'name="{call_url.split("?")[0]}"')
        if headers:
            h_serialized = json.dumps(headers, ensure_ascii=False)
            extra_kwargs.append(f"headers={h_serialized}")
        # Si hay body, formatear como json=... o data=...
        if body_kind and body_value:
            if body_kind == "json":
                try:
                    # Intentamos parsear para reindentar bonito
                    parsed = json.loads(body_value)
                    json_str = json.dumps(parsed, ensure_ascii=False)
                    extra_kwargs.append(f"json={json_str}")
                except json.JSONDecodeError:
                    # Si no es JSON válido, pasarlo crudo como data
                    extra_kwargs.append(f"data={body_value!r}")
            else:
                extra_kwargs.append(f"data={body_value!r}")

        kwargs_joined = ", ".join(extra_kwargs)
        call_url_repr = repr(call_url)  # repr = pone comillas y escapa caracteres
        code_lines.append(
            f"        self.client.request({method!r}, {call_url_repr}, {kwargs_joined})"
        )
        task_calls.append("\n".join(code_lines))

    # Ensamblar el cuerpo del método recorded_scenario()
    task_body = "\n\n".join(task_calls) if task_calls else "        pass"

    # -------- SUBPASO 2.6: ensamblar plantilla final de locustfile ----------
    # Usamos una triple-comilla con f-string para interpolar variables.
    # Las dobles {{ y }} son "llaves literales" en un f-string.
    template = f'''"""
Archivo generado automáticamente a partir de HAR: {os.path.basename(har_path)}
Fecha de generación: {__import__("datetime").datetime.now().isoformat(timespec="seconds")}
Cantidad de solicitudes mapeadas: {len(filtered_entries)}
Host base detectado: {base_url}
"""
from locust import HttpUser, TaskSet, between, task


class RecordedFlow(TaskSet):
    def on_start(self):
        pass

    @task
    def recorded_scenario(self):
{task_body}


class LoadUser(HttpUser):
    wait_time = between(1, 3)
    host = {base_url!r}
    tasks = {{RecordedFlow}}

    def on_start(self):
        pass
'''

    # -------- SUBPASO 2.7: Devolver (código_generado, info extra) -----------
    meta = {
        "base_url": base_url,
        "total_entries": str(len(entries)),
        "mapped_entries": str(len(filtered_entries)),
        "sample_cookies": json.dumps(sample_cookies, ensure_ascii=False),
    }
    return template, meta


# =============================================================================
# PASO 3 — PUNTO DE ENTRADA POR CONSOLA  (CLI: Command-Line Interface)
# =============================================================================
def main() -> None:
    """Lee argumentos de la línea de comandos y ejecuta la fachada convert_har()."""
    parser = argparse.ArgumentParser(description="Convierte un archivo HAR a locustfile.py")
    # Argumento posicional obligatorio: la ruta al .har
    parser.add_argument("har", help="Ruta al archivo HAR (ej: har_input/grabacion.har)")
    # Flag corto -largo + valor
    parser.add_argument("-o", "--output", default="locustfile.py", help="Archivo de salida")
    parser.add_argument("--base-url", default=None, help="Forzar URL base (ej: https://mi.api.com)")
    # Flags booleanos (si aparecen = True)
    parser.add_argument("--include-static", action="store_true", help="No omitir recursos estáticos (.css, .js, .png...)")
    parser.add_argument("--include-errors", action="store_true", help="No omitir respuestas 4xx/5xx")
    args = parser.parse_args()

    # Validación previa
    if not os.path.exists(args.har):
        raise SystemExit(f"ERROR: Archivo HAR no encontrado: {args.har}")

    # Llamada a la fachada
    template, meta = convert_har(
        args.har,
        base_url=args.base_url,
        skip_static=not args.include_static,  # flag invertido: "include" = no skip
        skip_errors=not args.include_errors,
    )

    # Escribir archivo a disco (usamos Path para manejar rutas seguras)
    out_path = Path(args.output)
    out_path.write_text(template, encoding="utf-8")

    # Reportar al usuario (consola) el resultado
    print(f"[OK] Generado: {out_path.resolve()}")
    print(f"     - Base URL       : {meta['base_url']}")
    print(f"     - Entradas HAR   : {meta['total_entries']}")
    print(f"     - Mapeadas       : {meta['mapped_entries']}")
    print(f"     - Cookies        : {meta['sample_cookies'][:200]}")


# =============================================================================
# GUARDA PYTHON: Si ejecutas este archivo directamente -> corre main(); si lo
# importas desde otro módulo como librería -> NO corre main().
# =============================================================================
if __name__ == "__main__":
    main()
