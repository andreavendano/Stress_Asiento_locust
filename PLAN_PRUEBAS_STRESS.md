# Plan de implementación – Pruebas de stress con Locust (Crear Asiento)

> **Estado:** borrador v2 · **Fecha:** 2026-11-05 · **Responsable:** QA Senior – Holistor
> **Repositorio:** `andreavendano/Stress_Asiento_locust`
> **Fuentes:**
> - Colección de Postman *"Carga · Crear Asiento multi-tenant (GDC, preparada para SYJ) · procesos aislados"*.
> - Documento del dev *"Servicios de Crear Asiento: orden de consumo y referencia"* (03/11/2026).
> - Pantalla *Contabilidad → Generar Asientos* y archivo `filas_performance.csv`.

---

## 1. Objetivo

Automatizar con **Locust** las pruebas de rendimiento (smoke, carga, stress, spike y resistencia) del circuito **Generar Asiento → Crear Asiento** (HU-05 / HU-07), para varios tenants, empresas, usuarios, períodos y tipos de asiento. El framework debe:

1. **Ser modular:** cada paso (login, selección de empresa y ejercicio, selección de período, origen y tipo de lote, generación, seguimiento de la cola, verificación) es un módulo propio y se **reutiliza** en cualquier escenario.
2. **Correr en varios ambientes** cambiando un solo parámetro (`--target-env`).
3. **No tener datos hardcodeados:**
   - Usuarios, tenants, empresas, períodos, tipos de lote y opciones de reemplazo salen de `users.csv`.
   - URLs, tiempos y umbrales salen del YAML del ambiente.
   - Las claves salen de variables de entorno.
4. **Medir lo que importa:** no solo el tiempo HTTP de cada servicio, sino el **tiempo de punta a punta** del asiento (encolado → Finalizado) y el **tiempo en cola** por tenant.
5. **Ser integrable a CI:** sale con código distinto de cero si no se cumplen los SLA.

---

## 2. Sistema bajo prueba

| Aspecto | Detalle |
|---|---|
| Backend QA | `https://gestor-comprobantes-back.azurewebsites.net`. Es el único ambiente; todavía no hay producción. |
| Frontend QA | `https://gestor-comprobantes-front.azurewebsites.net/dashboard/contabilidad/generar-asientos` |
| Framework | ABP (.NET). Las respuestas vienen envueltas en `{ success, data, error }`. |
| Multi-tenant | El `tenantId` se envía en el login. El encabezado opcional `x-tenant-name` separa la cola. |
| Swagger | `{{baseUrl}}/api/docs`. **Requiere sesión iniciada** (sin sesión devuelve 401). |
| Procesamiento | Asíncrono. Crear Asiento usa una **cola en memoria por tenant**. El `requestId` vive 30 minutos y se pierde si el servidor se reinicia. |

### 2.1 Circuito GDC (pantalla Generar Asientos)

Todos los servicios van bajo `/api/services/app/GdcGenerarAsientos`, salvo los indicados con ruta completa.

| # | Paso de negocio | Servicio | Qué devuelve o resuelve |
|---|---|---|---|
| 1 | Login | `POST /api/services/app/Account/Authenticate` `{email, password, tenantId}` | `data.accessToken` |
| 2 | Selección de empresa y ejercicio | `GET acceso?empCodigo=` | `data.ejercicios[]` (`codigo`, `fechaDesde`, `fechaHasta`) y `ejercicioSeleccionadoCodigo` |
| 3 | Selección de período | `GET periodos?empCodigo=&ejCodigo=` | `data.periodos[]` (`codigo` AAAAMM, `desde`, `hasta`, `personalizado`) |
| 3b | Período fiscal | `POST /api/services/app/GdcPeriodo/GetPeriodosFiscales` `{page, limit, search}` | `periodoFiscalId` |
| 4 | Origen del asiento | `GET origenes` y `GET tipos-comprobante?origenAsientoId=` | `origenAsientoId`, `tipoLote`, `tipoComprobanteIds` |
| 5 | Pre-check (opcional) | `POST precheck-estructura` | Registros del lote. ⚠ Respuesta muy pesada: unos 2,8 KB por comprobante. |
| 6 | Generar asiento | `POST generar-asiento-comprobantes` | **202** con `requestId` y `asientos[]` |
| 7 | Seguir la cola | `GET crear-asiento/{requestId}/progreso` (la pantalla usa `POST jobs/estado`) | `estado`: En Cola → En Proceso → Finalizado / Error |
| 8 | Resultado | `GET crear-asiento/{requestId}` | `asientos[]` con `status` y `errores` |
| 9 | Control | `POST jobs/estado` y `POST resultado-proceso` | Tabla `nuc_AsientosOtrosModulos` y fechas de cada asiento |

### 2.2 Circuito SYJ (preparado, deshabilitado por defecto)

Login → `POST crear-asiento?esperar=false` con su propio `Asiento_Cabecera` → progreso → resultado.

- La fila de control de SYJ todavía se inserta a mano, así que `jobs/estado` y `resultado-proceso` no aplican.
- SYJ **no** debe usar `generar-asiento-comprobantes`, `persistir-vinculo` ni `respuesta-contabilizacion`.

---

## 3. Restricciones que condicionan el diseño

| # | Restricción | Consecuencia en Locust |
|---|---|---|
| R1 | **Sesión única por usuario:** si el mismo usuario vuelve a iniciar sesión, se invalida el token de la sesión anterior. | **Una fila de `users.csv` = un usuario virtual, en exclusiva.** El login se hace una sola vez en `on_start` y se re-loguea solo ante un 401. En modo distribuido, cada worker recibe filas distintas. **La concurrencia máxima es igual a la cantidad de usuarios de performance.** |
| R2 | La cola de Crear Asiento es **por tenant**. | Con todas las filas en el tenant 866, los trabajos se encolan entre sí. El tiempo en cola **es** la métrica de stress principal. Para escalar de verdad hacen falta varios tenants. |
| R3 | `reemplazar = true` (`Marca_Borrar = S`) borra y recrea los asientos del mismo mes, tipo y módulo. | Permite repetir iteraciones sin acumular datos. **Dos usuarios virtuales con la misma combinación empresa / módulo / tipo / mes se pisarían**, por eso el loader lo valida. |
| R4 | `precheck-estructura` devuelve el lote completo (13.738 comprobantes ≈ 38 MB). | Es configurable: `off`, `primer_mes` o `completo`. Por defecto se ejecuta **una vez en `on_start`** y solo para el primer mes. |
| R5 | El `requestId` dura 30 minutos en memoria. | El seguimiento tiene timeout configurable. Un 404 en `progreso` se informa como "requestId perdido" (por ejemplo, por un reinicio). |
| R6 | El mismo `ID` de asiento enviado en dos llamados crea dos asientos (SYJ). | El builder de SYJ genera **un GUID nuevo en cada envío**. |
| R7 | Se crean **asientos reales**. | Guardia de producción: si el ambiente está marcado `es_produccion: true`, no corre sin `--permitir-produccion`. |
| R8 | Los usuarios de performance (`GDC1` a `GDC20`) son dedicados. | No usarlos en Postman ni en la UI mientras corre Locust (por R1). |

> **Ventaja frente a Postman:** en Locust cada usuario virtual es una instancia con su propio contexto, así que desaparece el problema de *variables cruzadas entre usuarios virtuales* que la colección resuelve con `it_x@USUARIO` y el control anti-mezcla.

---

## 4. Principios de diseño

| Principio | Cómo se aplica |
|---|---|
| **Capas** | Configuración → Datos → API (1 función = 1 servicio) → Flujos de negocio → Tareas → Usuarios virtuales → Entrypoints. Cada capa conoce solo a la de abajo. |
| **Una responsabilidad por módulo** | `api/auth.py` solo autentica, `flows/seleccion.py` solo resuelve empresa, ejercicio y período, etc. |
| **Configuración externa** | YAML por ambiente + variables de entorno para las claves. Nada de URLs ni códigos en el código. |
| **Datos externos** | `users.csv` por ambiente, con **el mismo formato que `filas_performance.csv`** de Postman (un solo archivo sirve para las dos herramientas). Plantillas JSON para SYJ. |
| **Entrypoints delgados** | Los `locustfiles/*.py` solo importan. |
| **Fallar con información** | Cada falla lleva la etiqueta de la fila (`[GDC1 · E3064 · 202601-202606 · COMPRAS]`), igual que en la colección. |
| **Sin secretos en logs ni reportes** | Las claves nunca se loguean ni se escriben en los reportes. |

---

## 5. Arquitectura por capas

```
┌───────────────────────────────────────────────────────────────────────────┐
│ locustfiles/   smoke_contexto.py · asiento_gdc.py · asiento_mixto.py      │  ← solo imports
├───────────────────────────────────────────────────────────────────────────┤
│ users/         AsientoGdcUser · AsientoSyjUser   (heredan HolistorUser)   │
├───────────────────────────────────────────────────────────────────────────┤
│ tasks/         GenerarAsientoGdcTask · CrearAsientoSyjTask                │
├───────────────────────────────────────────────────────────────────────────┤
│ flows/         sesion        → iniciar_sesion, asegurar_token (401)       │
│                seleccion     → seleccionar_empresa_ejercicio,             │
│                                seleccionar_periodo, seleccionar_origen    │
│                gdc / syj     → generar_asiento_gdc, crear_asiento_syj     │
│                seguimiento   → esperar_finalizacion, obtener_resultado    │
│                verificacion  → verificar_destino, verificar_control       │
├───────────────────────────────────────────────────────────────────────────┤
│ api/           auth · ejercicio · periodo · origen · gdc · crear_asiento  │
│                · control   (request + validación HTTP; sin decisiones)   │
│ builders/      syj_asiento_builder (GUID, Marca_Borrar)                   │
├───────────────────────────────────────────────────────────────────────────┤
│ core/          bootstrap · base_user · context · pool exclusivo · métricas│
│                E2E · validators · thresholds · guardia de producción     │
│ data/          loader + validación de users.csv (pydantic)                │
│ config/        settings + loader (YAML + .env + variables de entorno)     │
│ reporting/     trabajos.csv · verificacion.sql · resumen                  │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Estructura de carpetas

```
Stress_Asiento_locust/
├── pyproject.toml                    # Paquete instalable (pip install -e .) + dependencias fijadas
├── locust.conf                       # Valores por defecto de Locust (sin datos de ambiente)
├── .env.example                      # HOLISTOR_QA_CLAVE=… (sin valores reales)
├── .gitignore                        # .env, reports/, data/**/users.csv
├── README.md
├── PLAN_PRUEBAS_STRESS.md
│
├── src/holistor_stress/
│   ├── config/   settings.py · loader.py
│   ├── data/     fila.py (modelo FilaCarga) · users_loader.py · validaciones.py
│   ├── core/     bootstrap.py · base_user.py · context.py · pool.py
│   │             metrics.py (E2E) · validators.py · thresholds.py · guardia.py · run_info.py
│   ├── api/      rutas.py · auth.py · ejercicio.py · periodo.py · origen.py
│   │             gdc.py · crear_asiento.py · control.py
│   ├── builders/ syj_asiento_builder.py
│   ├── flows/    sesion.py · seleccion.py · gdc.py · syj.py · seguimiento.py · verificacion.py
│   ├── tasks/    asiento_tasks.py
│   ├── users/    asiento_users.py
│   ├── shapes/   stages_shape.py
│   └── reporting/ trabajos.py · sql_verificacion.py
│
├── locustfiles/
│   ├── smoke_contexto.py             # Login + empresa + período + origen (NO crea asientos)
│   ├── asiento_gdc.py                # Generar Asiento GDC de punta a punta
│   └── asiento_mixto.py              # GDC + SYJ concurrentes (equivale a la carpeta 02 de Postman)
│
├── environments/   qa.yaml  (dev.yaml, staging.yaml… cuando existan)
├── profiles/       smoke.conf · load.conf · stress.yaml · spike.yaml · soak.conf
├── data/
│   ├── qa/users.example.csv          # Versionado, sin claves
│   ├── qa/users.csv                  # NO versionado
│   └── plantillas/syj/*.json         # Asiento_Cabecera de SYJ (sin IDs fijos)
├── docs/referencia/                  # Colección de Postman, doc del dev, swagger.json exportado
├── scripts/        run.ps1 · run.sh
├── tests/          test_users_loader.py · test_seleccion_periodo.py · test_syj_builder.py · test_pool.py
└── reports/                          # NO versionado
```

> **¿Por qué `src/` + `pyproject.toml`?** Locust agrega al `sys.path` solo la carpeta del locustfile. Si el proyecto se instala como paquete (`pip install -e .`), cualquier entrypoint puede importar `holistor_stress.*`.

---

## 7. Configuración multi-ambiente

### 7.1 Precedencia (de mayor a menor)

1. Argumentos de línea de comando
2. Variables de entorno
3. `.env` local
4. `environments/<amb>.yaml`
5. Valores por defecto

### 7.2 `environments/qa.yaml` (ejemplo)

Los umbrales son **valores a acordar**, no definitivos.

```yaml
nombre: qa
base_url: "https://gestor-comprobantes-back.azurewebsites.net"
es_produccion: false            # true → exige --permitir-produccion
idioma: es                      # header Accept-Language
enviar_tenant_name: false       # header x-tenant-name (separa la cola)
timeout_request_s: 60

datos:
  users_csv: "data/qa/users.csv"
  plantillas_syj: "data/plantillas/syj"
  clave_env_var: "HOLISTOR_QA_CLAVE"   # se usa si la columna clave viene vacía

modulos:
  gdc: { habilitado: true }
  syj: { habilitado: false }    # requiere EmpMod, nuc_EjerEco y nuc_TipoAsiento (doc del dev)

flujo:
  contexto: una_vez             # una_vez | cada_iteracion (simula reabrir la pantalla)
  precheck: primer_mes          # off | primer_mes | completo
  seguimiento: progreso         # progreso | jobs_estado (lo que hace la pantalla de GDC)
  verificar_control: true       # POST jobs/estado al final (solo GDC)
  verificar_fechas: true        # POST resultado-proceso (solo GDC)
  polling: { intervalo_s: 3, timeout_s: 600 }
  relogin_401_max: 1

wait_time: { min_s: 5, max_s: 15 }   # "tiempo de pensar" entre trabajos (pausaMs en Postman)

thresholds:
  error_rate_max: 0.0
  p95_ms:
    "[Auth] Authenticate": 3000
    "[GDC] generar-asiento-comprobantes": 10000
  e2e_p95_s:
    "[E2E] GDC encolado→Finalizado": 120
```

### 7.3 Argumentos propios de Locust

Se registran con `events.init_command_line_parser`:

- `--target-env`: ambiente a usar.
- `--load-profile`: perfil de etapas.
- `--permitir-produccion`: habilita correr contra un ambiente marcado como producción.
- `--filtro-filas`: por ejemplo `modulo=GDC` o `tipoLote=VENTAS`, para correr un subconjunto sin editar el CSV.

---

## 8. Datos: `users.csv`

### 8.1 Columnas

Mismo esquema que la colección de Postman.

| Columna | Obligatoria | Descripción |
|---|---|---|
| `id` | sí | Nombre del trabajo (aparece en métricas, logs y reportes). |
| `activo` | no | `false` para saltear la fila. |
| `tenantId` | sí | Tenant del login. |
| `usuario` | sí | Email o usuario. **Único por tenant** (sesión única, R1). |
| `clave` | no* | Si viene vacía, se toma de la variable de entorno `clave_env_var`. *Debe resolverse por alguna de las dos vías. |
| `modulo` | sí | `GDC` o `SYJ`. |
| `empresa` | sí | `empCodigo`. |
| `periodo` | sí | `AAAAMM`, `AAAAMM-AAAAMM` o `TODOS`. |
| `tipoLote` | GDC | `COMPRAS`, `VENTAS`, `CERTIFICADOS_EMITIDOS` o `CERTIFICADOS_RECIBIDOS`. |
| `reemplazar` | no | GDC: `true` por defecto. SYJ: se traduce a `Marca_Borrar` (`S` / `N`, o vacío para respetar el JSON). |
| `plantilla` | SYJ | Archivo de `data/plantillas/syj/`. |
| `ejercicio` | no | Si no viene: en GDC se resuelve con el período y en SYJ sale de la plantilla. |
| `origenAsientoId` | no | Fuerza un origen (alternativa a `tipoLote`). |
| `comprobantesAIncluir` | no | `Todos` por defecto. |
| `periodoFiscalId` | no | Valor de respaldo si `GetPeriodosFiscales` no lo encuentra. |

Ejemplo de `users.example.csv`. La clave va vacía porque sale de `HOLISTOR_QA_CLAVE`:

```csv
id,activo,tenantId,usuario,clave,modulo,empresa,periodo,tipoLote,reemplazar,plantilla
T866-E3064-GDC1-COMPRAS-202601-202606,true,866,GDC1,,GDC,3064,202601-202606,COMPRAS,true,
```

### 8.2 Validaciones al cargar

Si alguna falla, la ejecución aborta antes de empezar y explica el motivo.

1. Campos obligatorios presentes según el módulo.
2. `periodo` con formato válido y `tipoLote` dentro de los valores permitidos.
3. **`(tenantId, usuario)` único**, por la sesión única (R1).
4. **Sin solapamiento** de `(tenantId, empresa, modulo, tipoLote, meses)` entre filas con `reemplazar = true` (R3).
5. Plantilla SYJ existente y con JSON válido.
6. **Usuarios pedidos ≤ filas activas.** Para perfiles con etapas se usa el máximo de la shape. Si no alcanza, la ejecución se detiene con el mensaje *"hay N filas activas y se pidieron M usuarios"*.

### 8.3 Pool exclusivo de filas

- `core/pool.py` entrega **una fila por usuario virtual** (sin ciclar).
- La fila se **devuelve en `on_stop`**: en stress y spike los usuarios virtuales bajan y suben, y un usuario nuevo puede reutilizar una fila liberada. Su login invalida un token que ya nadie usa.
- **Modo distribuido:** el master lee el CSV y envía a cada worker un subconjunto **disjunto** de filas por mensaje propio (`runner.register_message` / `send_message`). Así dos workers nunca loguean al mismo usuario.

---

## 9. Módulos reutilizables

### 9.1 Contexto del usuario virtual

```python
# core/context.py
@dataclass
class ContextoAsiento:
    fila: FilaCarga
    token: str | None = None
    ejercicio: Ejercicio | None = None          # codigo, desde, hasta
    periodo: PeriodoResuelto | None = None      # meses, fecha_desde, fecha_hasta, periodo_fiscal_id
    origen: OrigenResuelto | None = None        # origen_asiento_id, tipo_lote, tipo_comprobante_ids

    @property
    def etiqueta(self) -> str:                  # "[GDC1 · E3064 · 202601-202606 · COMPRAS]"
        ...
```

### 9.2 Capa API: una función por servicio

- Las rutas están centralizadas en `api/rutas.py`.
- Cada función recibe el `client` y el contexto, usa `name="[Grupo] servicio"` y `catch_response=True`, desenvuelve `data` de ABP y valida el código HTTP.

| Módulo | Funciones | Nombre en estadísticas |
|---|---|---|
| `auth` | `authenticate` | `[Auth] Authenticate` |
| `ejercicio` | `acceso` | `[GDC] acceso` |
| `periodo` | `periodos`, `periodos_fiscales` | `[GDC] periodos`, `[GDC] GetPeriodosFiscales` |
| `origen` | `origenes`, `tipos_comprobante` | `[GDC] origenes`, `[GDC] tipos-comprobante` |
| `gdc` | `precheck_estructura`, `generar_asiento_comprobantes` | `[GDC] precheck-estructura`, `[GDC] generar-asiento-comprobantes` |
| `crear_asiento` | `crear` (SYJ), `progreso`, `resultado` | `[CrearAsiento] crear`, `[CrearAsiento] progreso`, `[CrearAsiento] resultado` |
| `control` | `jobs_estado`, `resultado_proceso` | `[Control] jobs/estado`, `[Control] resultado-proceso` |

### 9.3 Capa de flujos: los pasos que se reutilizan

| Flujo | Qué hace | Lógica que se trae de la colección |
|---|---|---|
| `sesion.iniciar_sesion` | Login con la fila. Guarda el token en el contexto. | Body `{email, password, tenantId}` |
| `sesion.asegurar_token` | Ante un 401 re-loguea hasta `relogin_401_max` veces y reintenta. Si vuelve a fallar, informa **"sesión invalidada (¿usuario usado en otra sesión?)"**. | Descarte del token ante un 401 |
| `seleccion.seleccionar_empresa_ejercicio` | `acceso` → valida la empresa y elige el ejercicio de la fila o el que contiene el primer mes del período. | 01.2 |
| `seleccion.seleccionar_periodo` | `periodos` → filtra los meses no personalizados del rango (`AAAAMM`, rango o `TODOS`) y avisa los meses que quedan fuera del ejercicio. Luego `GetPeriodosFiscales` → `periodoFiscalId`. | 01.3 |
| `seleccion.seleccionar_origen` | `origenes` (`esComprobante`) → `tipos-comprobante` hasta encontrar el `tipoLote` de la fila. | 01.4 |
| `gdc.precheck` | Opcional (R4). Primero consulta el primer mes y solo usa el rango completo si ese mes está vacío. | 01.4 |
| `gdc.generar_asiento_gdc` | Arma el body con el contexto → espera 202 con `requestId` y `asientos[]`. | 01.5 |
| `syj.crear_asiento_syj` | Builder: plantilla + GUID nuevo + `Marca_Borrar` → `crear-asiento?esperar=false`. | 01.6 |
| `seguimiento.esperar_finalizacion` | Consulta `progreso` (o `jobs/estado`) cada `intervalo_s` hasta Finalizado o Error, o hasta `timeout_s`. Registra cuánto tiempo estuvo En Cola. | 01.7 |
| `seguimiento.obtener_resultado` | `GET crear-asiento/{id}` → resultado de cada asiento. | 01.7 |
| `verificacion.verificar_destino` | Todos los asientos OK, uno por cada enviado, IDs devueltos iguales a los enviados, empresa y ejercicio correctos, fechas dentro del período. | 01.7 |
| `verificacion.verificar_control` | GDC: `jobs/estado` con todos aceptados y ninguno pendiente ni rechazado. | 01.7 |

### 9.4 Ciclo de vida del usuario virtual

```python
# core/base_user.py (ilustrativo)
class HolistorUser(HttpUser):
    abstract = True

    def wait_time(self):                                   # leído de la configuración
        wt = self.environment.holistor.settings.wait_time
        return random.uniform(wt.min_s, wt.max_s)

    def on_start(self):
        fila = self.environment.holistor.pool.tomar()      # exclusiva (R1)
        self.ctx = ContextoAsiento(fila=fila)
        iniciar_sesion(self)                               # una sola vez
        preparar_contexto(self)                            # empresa + ejercicio + período + origen (+ precheck)

    def on_stop(self):
        self.environment.holistor.pool.devolver(self.ctx.fila)
```

```python
# tasks/asiento_tasks.py (ilustrativo)
class GenerarAsientoGdcTask(TaskSet):
    @task
    def trabajo(self):
        u = self.user
        if settings.flujo.contexto == "cada_iteracion":
            preparar_contexto(u)                           # reabre la pantalla
        envio = generar_asiento_gdc(u)
        with medir_e2e(u, "[E2E] GDC encolado→Finalizado", envio):
            prog = esperar_finalizacion(u, envio.request_id)
        res = obtener_resultado(u, envio.request_id)
        verificar_destino(u, envio, res)
        verificar_control(u, envio)
        registrar_trabajo(u, envio, prog, res)             # → reports/…/trabajos.csv
```

Si falla la preparación del contexto (empresa sin ejercicio, período fuera de rango, lote sin comprobantes), el usuario virtual registra la falla `[Setup] …`, devuelve su fila y se detiene con `StopUser`. No martilla el servidor con una fila inválida.

### 9.5 Cómo se reutiliza

- `smoke_contexto` usa solo `iniciar_sesion` + `preparar_contexto`. Sirve para verificar un ambiente **sin crear asientos**.
- `asiento_gdc` y `asiento_mixto` reutilizan esos mismos pasos y agregan generación, seguimiento y verificación.
- SYJ reutiliza el login, el seguimiento y la verificación. Solo cambia el paso de envío.

---

## 10. Métricas

### 10.1 HTTP

Locust las mide de forma nativa, agrupadas por los nombres de la tabla 9.2.

### 10.2 Métricas de negocio (E2E)

El HTTP de `generar-asiento-comprobantes` responde rápido (202), pero el trabajo real ocurre en la cola. `core/metrics.py` publica métricas propias con `events.request.fire(request_type="E2E", …)`, que aparecen en las mismas tablas, gráficos y CSV de Locust:

| Métrica | Desde → hasta |
|---|---|
| `[E2E] GDC encolado→Finalizado` | Envío del 202 → estado Finalizado |
| `[E2E] GDC tiempo En Cola` | Envío → primer estado distinto de En Cola |
| `[E2E] GDC tiempo de proceso` | Primer En Proceso → Finalizado |
| `[E2E] SYJ encolado→Finalizado` | Ídem para SYJ |
| `[E2E] Trabajo completo` | Generar + seguir + verificar. Es una falla si algún asiento no queda OK o si el control no coincide. |

También se calcula el **throughput de asientos** (asientos OK por minuto) por tenant.

---

## 11. Validaciones y SLA

1. **Por request:** código HTTP esperado (`202` en generar, `200` en el resto), `data` presente y sin errores 5xx. Equivale a los tests `[NFR]` de la colección.
2. **Por trabajo:** las verificaciones de la sección 9.3, con la etiqueta de la fila en el mensaje. Si un asiento vuelve con *"Error al crear archivo"*, el mensaje sugiere revisar `EmpMod`, `nuc_EjerEco` y `nuc_TipoAsiento`.
3. **Entre trabajos (al cierre):** **ningún ID de asiento aparece en la salida de dos trabajos distintos.** Es el control de concurrencia de la carpeta 02 de Postman.
4. **Por corrida:** en `events.quitting` se comparan `thresholds` (tasa de error, p95 HTTP y p95 E2E). Si se supera alguno, `process_exit_code = 1`.

---

## 12. Perfiles de carga

Por la restricción R1, el **techo actual es de 20 usuarios virtuales** (`GDC1` a `GDC20`, todos en el tenant 866). Para superarlo hacen falta más usuarios y, para aliviar la cola (R2), más tenants.

| Perfil | Objetivo | Propuesta inicial (a acordar) |
|---|---|---|
| **Smoke** | Verificar el script y el ambiente | `smoke_contexto` con 2 usuarios, y luego `asiento_gdc` con 1 usuario y 1 iteración |
| **Load** | Concurrencia esperada | N usuarios (definir con producto) durante 30 minutos |
| **Stress** | Encontrar el punto de quiebre de la cola | Escalones de 5 → 10 → 15 → 20 usuarios, cada uno de X minutos |
| **Spike** | Cierre de mes: todos generan a la vez | De 0 a 20 usuarios de golpe, sin `wait_time` |
| **Soak** | Fugas de memoria, expiración de tokens y cola en memoria | 10 usuarios durante 2 a 4 horas |

- Los perfiles con etapas usan `StagesShape`, que lee `profiles/<perfil>.yaml`.
- Se cargan como un locustfile adicional: `-f locustfiles/asiento_gdc.py,src/holistor_stress/shapes/stages_shape.py`.

---

## 13. Ejecución

```powershell
$env:HOLISTOR_QA_CLAVE = "<clave>"            # o en .env
./scripts/run.ps1 -Env qa -Profile smoke  -Scenario smoke_contexto
./scripts/run.ps1 -Env qa -Profile stress -Scenario asiento_gdc -Headless
./scripts/run.ps1 -Env qa -Profile load   -Scenario asiento_gdc -Filtro "tipoLote=VENTAS"
```

El script resuelve el locustfile, la shape y la configuración, y crea `reports/<amb>_<escenario>_<perfil>_<timestamp>/`.

**Modos:**

- **UI local:** para depurar.
- **Headless:** para ejecuciones planificadas y CI.
- **Distribuido:** master y workers, con reparto de filas (sección 8.3).
- **CI:** smoke automático. Load y stress se disparan a mano o de forma programada.

---

## 14. Reportes y evidencia

Equivale al resumen 99.1 de la colección. Cada corrida deja en su carpeta:

| Archivo | Contenido |
|---|---|
| `report.html`, `stats*.csv` | Reporte nativo de Locust (HTTP + E2E) |
| `trabajos.csv` | Una fila por trabajo: fila, tenant, usuario, módulo, empresa, ejercicio, rango, tipo, `requestId`, asientos OK/total, segundos, segundos En Cola, consultas a progreso, estado de la tabla de control, resultado y errores |
| `verificacion.sql` | Consultas para ejecutar en la base del tenant: estado en `nuc_AsientosOtrosModulos` por ID, asientos en `nuc_AsientoCabecera` por empresa / ejercicio / módulo / período y requisitos de SYJ (`EmpMod`, `nuc_EjerEco`, `nuc_TipoAsiento`, cuentas y centros de costo) |
| `run.log` | Log de la corrida, sin claves |
| `run_info.json` | `run_id`, ambiente, perfil, versión del framework y parámetros |

---

## 15. Observabilidad

- Durante load, stress y soak: métricas del App Service de Azure (CPU, memoria, hilos, reinicios) y de SQL (DTU/CPU, bloqueos, consultas lentas sobre `nuc_AsientoCabecera`, `nuc_AsientoDetalle` y `nuc_Saldos`).
- Un reinicio del servidor pierde la cola en memoria (R5). Si `progreso` empieza a devolver 404, hay que correlacionarlo con los reinicios del App Service.
- Plantilla de informe por corrida: objetivo, ambiente, versión, perfil, resultados vs. SLA, cuellos de botella y recomendaciones.

---

## 16. Calidad del framework

- `ruff` y `pytest`. Hay pruebas unitarias para la resolución de período y ejercicio, la validación del CSV, el pool exclusivo y el builder de SYJ. Son funciones puras y se prueban sin servidor.
- Pre-commit con `ruff` y detección de secretos (`detect-secrets` o `gitleaks`).
- Dependencias fijadas: Locust 2.x, pydantic, pydantic-settings, PyYAML y python-dotenv.
- Convenciones: dominio en español, nombres de request `[Grupo] servicio`, un archivo por grupo de servicios.

---

## 17. Cómo agregar un caso nuevo (ejemplo: Posición Mensual IVA, paso 5b del doc)

1. Agregar las rutas en `api/rutas.py` y las funciones en `api/posicion_iva.py`: `liquidaciones-iva`, `validar-cuentas-faltantes-posicion-mensual` y `generar-asiento-posicion-mensual`.
2. Crear `flows/posicion_iva.py` → `generar_asiento_posicion_iva(user)`.
3. Agregar un `tipoLote` o un `modulo` nuevo en `users.csv` y su validación en `data/validaciones.py`.
4. Crear una task en `tasks/` que **reutilice** `esperar_finalizacion`, `obtener_resultado` y `verificar_control`.
5. Crear un entrypoint nuevo o sumarlo con peso a `asiento_mixto`.

El login, la selección de empresa, ejercicio y período, el seguimiento y la verificación **no se tocan**.

---

## 18. Plan de trabajo por fases

| Fase | Entregables | Criterio de terminado |
|---|---|---|
| **0. Relevamiento** ✅ parcial | Colección de Postman y doc del dev analizados. **Pendiente:** swagger exportado, SLA, volúmenes y vida del token (sección 20). | Preguntas abiertas respondidas |
| **1. Esqueleto** ✅ | `pyproject.toml`, configuración, loader y validación de `users.csv`, pool exclusivo, guardia de producción, `.gitignore`, README, tests unitarios | `locust --target-env qa` valida configuración y datos y aborta con mensajes claros |
| **2. Contexto reutilizable** ✅ | `api/` (auth, ejercicio, periodo, origen, precheck), `flows/sesion` y `flows/seleccion`, `HolistorUser`, `smoke_contexto`, servidor simulado | Smoke con 20 usuarios en paralelo, sin 401 por sesión cruzada y sin crear asientos. Verificado en QA (05/11: 20 logins, 0 fallas, 0 sesiones cruzadas) |
| **3. GDC de punta a punta** ✅ código (pendiente: corrida en QA) | `api/gdc`, `api/crear_asiento`, `api/control`, flujos de generación, seguimiento y verificación, métricas E2E, `trabajos.csv` | `asiento_gdc` con 1, 5 y 20 usuarios, con todas las verificaciones en verde |
| **4. Perfiles y SLA** | `profiles/*`, `StagesShape`, `thresholds`, `run.ps1` y `run.sh`, `verificacion.sql` | Cada perfil ejecuta y el código de salida refleja los SLA |
| **5. SYJ y mixto** | Builder de SYJ, `flows/syj`, `asiento_mixto`, control "ningún ID en dos trabajos" | GDC y SYJ concurrentes en el mismo tenant y empresa, en verde (cuando SYJ esté habilitado) |
| **6. Escala y CI** | Modo distribuido con reparto de filas, pipeline de CI y publicación de reportes | Smoke en el pipeline y load programable |
| **7. Ampliación** | Posición Mensual IVA, asignación de cuentas, etc. (sección 17) | Casos nuevos sin modificar los módulos existentes |

---

## 19. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Sesión cruzada: un usuario de performance usado en otra sesión | Usuarios dedicados, validación de unicidad, re-login controlado y métrica explícita de "sesión invalidada" |
| Techo de 20 usuarios virtuales (R1) | Pedir más usuarios de performance y más tenants. Mientras tanto, medir la saturación de la cola con 20 usuarios y spike. |
| `precheck-estructura` satura la máquina generadora (38 MB) | `primer_mes` por defecto, una sola vez en `on_start` |
| Reinicio del App Service: cola y `requestId` perdidos | Timeout y 404 informados como falla específica; correlacionar con Azure |
| Datos que se agotan (lotes sin comprobantes) | Validación en `on_start` (precheck) y `reemplazar = true` para repetir sobre el mismo lote |
| Claves filtradas | `users.csv` fuera de git, clave por variable de entorno, sin claves en logs ni reportes, pre-commit con detección de secretos |
| Ejecución accidental contra producción | Guardia `es_produccion` + `--permitir-produccion` |

---

## 20. Preguntas abiertas

1. **Swagger:** pide sesión. ¿Podés exportar el JSON (desde `/api/docs` con sesión iniciada) y dejarlo en `docs/referencia/swagger.json`? Sirve para confirmar los contratos y para encontrar los servicios de los modales *Seleccionar Empresa* y *Seleccionar Período Fiscal* de la cabecera, por si queremos simular también esa navegación.
2. **Vida del token:** ¿cuánto dura el `accessToken`? Define cómo se comporta el soak.
3. **Volúmenes reales:** ¿cuántos usuarios generan asientos a la vez en un cierre de mes? ¿Cuántos asientos por hora?
4. **SLA:** ¿qué tiempo de punta a punta (encolado → Finalizado) es aceptable para un trabajo de 6 meses? ¿Qué tasa de error?
5. **Escala:** ¿se pueden crear más usuarios de performance (`GDC21`…) y otros tenants con datos, para pasar el techo de 20 y probar varias colas?
6. **Seguimiento:** ¿simulamos lo que hace la pantalla de GDC (`jobs/estado`) o lo que hace la colección (`progreso`)? El plan deja las dos opciones configurables.
7. **SYJ:** ¿cuándo se habilita en QA? ¿Las empresas y plantillas ya cumplen `EmpMod`, `nuc_EjerEco` y `nuc_TipoAsiento`?
8. **`periodoFiscalId`:** si `GetPeriodosFiscales` no lo encuentra, la colección usa `1`. ¿Es correcto o conviene fallar? *(Mientras tanto es configurable: `flujo.periodo_fiscal_id_defecto`, `null` = fallar.)*
9. **Monitoreo:** ¿hay acceso a las métricas del App Service y de la base durante las corridas?
10. **CI:** ¿Azure DevOps / TFS u otra herramienta?
