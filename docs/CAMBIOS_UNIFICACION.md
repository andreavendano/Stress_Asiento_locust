# Unificación con los escenarios de comprobantes (rama `feature/unificacion-escenarios`)

Notas para revisar el PR. Se sumaron a este repositorio los escenarios de carga de **Gestor de Comprobantes** que
estaban en otro proyecto (`stress_test`), para tener un solo repositorio:

- importación de comprobantes de compra,
- modificación masiva de cabecera,
- crear comprobante de compra (variante lite y flujo completo de 113 pasos),
- sondeo de "importación en curso" y utilidades sueltas.

**Los escenarios de asientos (`asiento_gdc`, `smoke_contexto`) no cambian de comportamiento.** Los 122 tests originales
pasan sin modificarse y los dos locustfiles se corrieron contra `tests/servidor_simulado.py` con un `users.csv` mixto:
terminan OK y toman solo sus filas GDC.

## 1. Cambios en archivos existentes

Todos son agregados u opcionales con un valor por defecto que reproduce lo de antes. Sin tocar: flows `gdc`,
`seleccion`, `seguimiento`, `verificacion`, `trabajo_gdc`, `contexto`, `bd/` y `reporting/` (salvo el registro nuevo).

| Archivo | Cambio | Por qué | Efecto en asientos |
|---|---|---|---|
| `data/fila.py` | `modulo` acepta además `IMPO`, `MODIF`, `CPBTE`. Columnas opcionales `login` (`gdc` por defecto / `plataforma`) y `tenancy`. Los módulos nuevos exigen un único mes; `login=plataforma` exige `tenancy`. La etiqueta muestra `usuario@tenancy` si hay `tenancy` | Un solo `users.csv` para todos los escenarios. Las cuentas de comprobantes son `admin` por tenant y se loguean por la plataforma | Ninguno (sus filas no traen `tenancy`) |
| `data/preparacion.py` | Parámetro opcional `modulos`: deja solo las filas de esos módulos (`excluidas_por_escenario`). Valida empresa única por importación y que haya sección `plataforma:` si alguna fila la usa | Cada locustfile toma solo las filas de su módulo | ⚠ Ver nota 1 |
| `data/validaciones.py` | Nuevas `validar_empresa_unica_importacion` y `validar_login_plataforma` | El back permite una importación a la vez por empresa | Ninguno |
| `core/bootstrap.py` | `_modulos_del_escenario()`: lee `modulos_fila` de las clases de usuario del locustfile y se lo pasa al runtime. Si alguna clase no lo declara, se usan todas las filas (como antes). El resumen final informa también los ciclos | Filtrar filas por escenario sin tocar la línea de comando | Ninguno |
| `core/runtime.py` | `modulos` opcional; la guardia de producción también revisa `plataforma.host_url` y `front_url`; registro `ciclos.csv` | El login por plataforma y el stream de la importación tocan esos hosts | Ninguno (`ciclos.csv` solo se crea si hay ciclos) |
| `core/base_user.py` | Atributo `modulos_fila = None` y dos puntos de extensión: `nuevo_contexto(fila)` y `preparar_contexto(con_precheck)`. Por defecto hacen exactamente lo de antes (`ContextoAsiento` + `flows.contexto.preparar_contexto`) | Los usuarios de comprobantes resuelven datos maestros en lugar de la pantalla Generar Asientos | Ninguno |
| `core/context.py` | Campos opcionales `abp_tenant_id` y `user_id` en `ContextoAsiento` | Login por plataforma: header `Abp.TenantId` y `userId` | Ninguno (quedan en `None`) |
| `api/http.py` | `llamar` acepta opcionales `headers`, `data` (multipart), `crudo` (JSON completo, sin desenvolver) y `exigir_success`. Agrega `Abp.TenantId` solo si el contexto lo tiene. Nueva función `navegar()` para requests de navegación que no cortan el flujo | Servicios de comprobantes con datos fuera de `data` y la navegación del flujo completo | ⚠ Ver nota 2 |
| `api/auth.py` | Nueva `authenticate_plataforma()` (IsTenantAvailable + TokenAuth/Authenticate). `authenticate()` no cambió | Login de las cuentas `admin` | Ninguno |
| `api/rutas.py` | Rutas y nombres nuevos al final | — | Ninguno |
| `flows/sesion.py` | `iniciar_sesion` usa `authenticate_plataforma` si la fila tiene `login=plataforma`; si no, el mismo código de antes | — | Ninguno |
| `config/settings.py` | Secciones nuevas opcionales: `plataforma`, `maestros`, `importacion`, `modificacion`; módulos `impo`, `modif`, `cpbte` | Reemplazan las variables `IMPO_*` / `MODIF_*` / `TARGET_ENV` del proyecto anterior | Ninguno |
| `users/asiento_users.py`, `users/smoke_users.py` | `modulos_fila = ("GDC",)` y `("GDC", "SYJ")` | Que no tomen filas de los módulos nuevos | Ninguno con su `users.csv` actual |
| `environments/qa.yaml` | Secciones `plataforma`, `maestros`, `importacion`, `modificacion` y los tres módulos nuevos | — | Ninguno |
| `data/qa/users.example.csv` | Dos columnas al final (`login`, `tenancy`, vacías en sus filas) y 6 filas de ejemplo de comprobantes | — | Ninguno |
| `README.md` | Tabla de escenarios al inicio, columnas nuevas de `users.csv`, estructura y sección "Migración desde stress_test" | — | — |

**Nota 1 – sesión única en `holistor-stress-check`.** Sin escenario (la CLI de verificación sin `modulos`), la
validación de usuarios repetidos ahora se hace **por módulo**: las cuentas `admin` aparecen en IMPO, MODIF y CPBTE, y
se corre un escenario por vez. En las corridas de Locust se sigue validando sobre todas las filas del escenario.
Consecuencia: si algún día GDC y SYJ comparten un usuario, la CLI ya no lo marca (el locustfile sí).

**Nota 2 – mensajes de error.** `detalle_error` además incluye `code` (si no hay otro mensaje) y `errors` cuando el
servidor los manda. En los servicios de asientos no aparecen, así que los mensajes no cambian.

## 2. Archivos nuevos

```
locustfiles/importacion_compras.py, modificacion_masiva.py, comprobante_compra_lite.py,
            comprobante_compra_completo.py, sondeo_importacion.py
src/holistor_stress/
  api/comprobantes.py      gdc() (llamar + JSON completo + success=false es falla + nombre del paso en el error),
                           grilla de compras, crear y leer comprobante
  api/maestros.py          empresa, períodos fiscales, proveedor, tipos de movimiento
  api/importacion.py       los 15 servicios de la importación y el stream SSE del job
  core/contexto_comprobantes.py   Maestros y ContextoComprobantes (subclase de ContextoAsiento)
  core/shapes.py           rampa escalonada opcional (LOAD_SHAPE=steps)
  flows/maestros.py        resolución de datos maestros, con cache por tenant/empresa/período
  flows/ciclo.py           ciclo común: fila FLUJO "XXX 00", errores aparte (VALIDACION), [XXX RESUMEN], ciclos.csv
  flows/importacion.py, modificacion.py, comprobante.py
  flows/pasos_comprobante_completo.py   tabla de los 113 pasos, generada a partir del archivo original
  reporting/ciclos.py      ciclos.csv
  tasks/comprobantes_tasks.py, users/comprobantes_users.py
data/plantillas/importacion/plantilla_importacion_compras_oficial.csv   solo el encabezado (formato Portal IVA)
docs/ESCENARIO_IMPORTACION.md, ESCENARIO_MODIFICACION_MASIVA.md, ESCENARIO_CREAR_COMPROBANTE.md
tests/servidor_comprobantes.py   simulador de la plataforma y de los servicios de comprobantes (en memoria y HTTP)
tests/test_comprobantes.py       31 tests
tools/                           har_to_locust, blazemeter_json_to_locust, lote de 20.000 comprobantes
```

Se respetaron las capas del proyecto (`locustfile → users → tasks → flows → api → http.llamar`) y la jerarquía de
fallas de `core/errores.py`: falla de datos → el usuario se detiene; HTTP transitoria → se reintenta; 401 → re-login;
falla del ciclo (`FallaTrabajo`) → se registra y sigue con el próximo.

## 3. Correcciones respecto del proyecto anterior

- **Modificación masiva, `MODIF 07`:** releía la página con `limit = cantidad leída`. Si la página al azar era la
  última e incompleta, comparaba otra ventana de la grilla y el ciclo fallaba sin motivo. Ahora relee con el mismo
  tamaño de página (test de regresión).
- **Herencia de tareas:** Locust suma las `tasks` de la clase base a las de cada subclase, así que en el sondeo a veces
  se ejecutaba la tarea de ciclo. Por eso `ComprobantesUser` no declara `tasks`: cada usuario concreto declara la suya
  (test de regresión).

## 4. Verificación

- `pytest`: 153 tests (122 originales + 31 nuevos). `ruff check src tests locustfiles`: sin errores.
- Locust contra los simuladores: los 4 escenarios nuevos + sondeo, y `asiento_gdc` / `smoke_contexto`.
- **QA real** (10/11/2026, 1 usuario y 1 ciclo cada uno; cada corrida creó o modificó datos reales):

| Escenario | Tenant | Resultado |
|---|---|---|
| Comprobante lite | QA7 | OK: comprobante 226324 |
| Comprobante completo | QA7 | OK: comprobante 226325, 120 requests sin fallas |
| Importación (28) | QA6 | OK: 8000 → 8028 comprobantes, job COMPLETED |
| Modificación masiva (50) | QA6 | OK: 50/50 con los valores nuevos |
| Sondeo | QA6 + QA7 | OK |

En QA7, la empresa 6 tiene una importación trabada ("procesando", período 10/2024). Mientras siga así, el paso
`IMPO 02` corta a los 600 s con ese motivo, que es lo esperado.

## 5. Qué no se versiona

- `data/qa/users.csv`: lleva las claves de las cuentas `admin` en la columna `clave` (está en `.gitignore`).
- Las grabaciones de BlazeMeter/JMeter (`har_input/*.json`) del proyecto anterior: tienen tokens JWT y una clave.
- Las filas de datos de la plantilla de importación (eran comprobantes reales): queda solo el encabezado.
