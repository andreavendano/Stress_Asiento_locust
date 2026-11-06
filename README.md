# Stress Asiento – Locust

Pruebas de rendimiento (smoke, carga, stress, spike y soak) del circuito **Generar Asiento → Crear Asiento** de Holistor, con Locust.

El diseño completo y el plan por fases están en [PLAN_PRUEBAS_STRESS.md](PLAN_PRUEBAS_STRESS.md).

> **Estado:** Fase 3 (GDC de punta a punta).
> - Fase 1: configuración multi-ambiente, validación de `users.csv`, pool exclusivo y guardia de producción.
> - Fase 2: capa API, flujos de sesión y selección, `HolistorUser` y `smoke_contexto` (no crea asientos).
> - Fase 3: `asiento_gdc` genera asientos reales, sigue la cola hasta Finalizado, verifica destino, fechas y tabla de control, publica métricas E2E y deja `trabajos.csv`.

## Generar asientos GDC de punta a punta (`asiento_gdc`)

> ⚠ **Crea asientos reales.** Con `reemplazar=true` (el valor por defecto en GDC) borra y recrea los asientos del mismo mes, tipo y módulo de cada fila.

Conviene ir de menor a mayor:

```powershell
# 1) Un usuario, un trabajo: la prueba termina sola
locust -f locustfiles/asiento_gdc.py --target-env qa --headless -u 1 -r 1 -t 20m --trabajos-por-usuario 1

# 2) Cinco usuarios a la vez, un trabajo cada uno
locust -f locustfiles/asiento_gdc.py --target-env qa --headless -u 5 -r 5 -t 30m --trabajos-por-usuario 1

# 3) Los 20 usuarios a la vez (cierre de mes), un trabajo cada uno
locust -f locustfiles/asiento_gdc.py --target-env qa --headless -u 20 -r 20 -t 40m --trabajos-por-usuario 1

# 4) Carga sostenida: 20 usuarios durante 30 minutos, sin cuota
locust -f locustfiles/asiento_gdc.py --target-env qa --headless -u 20 -r 2 -t 30m
```

- Con `--trabajos-por-usuario N`, cada usuario virtual hace N trabajos y la prueba termina cuando terminan todos. `-t` queda como tope de seguridad.
- La salida de cada corrida queda guardada sola (ver [Resultados de cada corrida](#resultados-de-cada-corrida)).

Métricas de negocio (aparecen en las mismas tablas de Locust, tipo `E2E`):

| Nombre | Desde → hasta |
|---|---|
| `[E2E] GDC encolado→Finalizado` | 202 de generar → estado Finalizado. Es una falla si termina en Error |
| `[E2E] GDC tiempo En Cola` | 202 → primera consulta con un estado distinto de En Cola |
| `[E2E] GDC tiempo de proceso` | Primera consulta En Proceso → Finalizado |
| `[E2E] Trabajo completo` | Generar + seguir + verificar. Es una falla si algún asiento no queda OK o si alguna verificación no cierra |

Los tiempos E2E tienen la resolución de `flujo.polling.intervalo_s` (3 s por defecto).

Un trabajo es una falla en cualquiera de estos casos:

- La cola termina en Error o no termina en `flujo.polling.timeout_s`.
- Un 404 en progreso: el `requestId` se perdió.
- Algún asiento no queda OK. Si el error es *"Error al crear archivo"*, el mensaje sugiere revisar EmpMod, nuc_EjerEco y nuc_TipoAsiento.
- Algún asiento queda con otra empresa o ejercicio, o los IDs devueltos no son los enviados.
- Alguna fecha queda fuera del período.
- La tabla de control tiene asientos pendientes o rechazados.
- Un ID de asiento ya se había devuelto en el trabajo de otra fila.

Ante una falla, el usuario virtual sigue con el próximo trabajo.

## Instalación

Requiere Python 3.11 o superior.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,bd]"
```

## Datos y claves

1. Copiar `data/qa/users.example.csv` como `data/qa/users.csv`. Ese archivo **no se versiona**: está en `.gitignore`.
2. Copiar `.env.example` como `.env` y completar `HOLISTOR_QA_CLAVE`.
   - Esa variable se usa en todas las filas cuya columna `clave` venga vacía.
   - También se puede definir como variable del sistema o como secreto del CI.

`users.csv` usa las mismas columnas que `filas_performance.csv` de la colección de Postman. Cada fila es **un usuario virtual exclusivo**, porque la aplicación permite una sola sesión por usuario.

## Verificar configuración y datos (sin generar carga)

```powershell
holistor-stress-check --target-env qa
holistor-stress-check --target-env qa --users 20 --filtro-filas "tipoLote=VENTAS"
```

El comando valida lo siguiente y explica cada error que encuentra:

- La configuración del ambiente.
- La guardia de producción.
- El formato de cada fila.
- Que no haya usuarios repetidos (sesión única).
- Que dos filas no reemplacen los mismos asientos.
- Las plantillas de SYJ.
- Que haya filas suficientes para la cantidad de usuarios pedida.

Códigos de salida: `0` = OK, `1` = configuración o datos inválidos, `2` = bloqueado por la guardia de producción.

## Resultados de cada corrida

Toda ejecución de Locust (smoke o asientos) guarda su salida en `reports/<run_id>_<escenario>_<N>u/`, o en `--carpeta-reportes`. No hace falta pasar `--csv` ni `--html`.

| Archivo | Contenido |
|---|---|
| `reporte.html` | **Informe legible de la corrida.** Tiene indicadores, el tiempo de cada trabajo (En Cola + proceso), la evolución durante la prueba (usuarios, req/s, p95 y trabajos), los umbrales, los servicios y las fallas. Se abre sin conexión |
| `resumen.md` | El mismo resumen en Markdown, para pegar en el informe o en un ticket |
| `resumen.json` | El resumen en formato de máquina, para consolidar corridas |
| `trabajos.csv` | Una fila por trabajo, separado por `;` para Excel: `requestId`, asientos OK/total, segundos totales, En Cola y de proceso, tabla de control, resultado, errores e IDs |
| `historial.csv` | Una muestra cada 5 s: usuarios, req/s, fallas/s, p50/p95 y trabajos terminados |
| `locust_stats.csv`, `locust_failures.csv`, `locust_exceptions.csv` | Tablas de Locust con su formato nativo, en UTF-8 (incluyen las métricas E2E) |
| `locust_report.html` | Reporte nativo de Locust |
| `run.log` | Log de la corrida (sin claves) |
| `run_info.json` | Parámetros, umbrales, configuración del flujo, inicio, fin, duración y código de salida |
| `verificacion.sql` | Consultas para la base del tenant. Por trabajo: asientos OK en `nuc_AsientosOtrosModulos` y comprobantes contabilizados con esos GUID (`CCpraGUIDAsiento` / `CVtaGUIDAsiento`), que es la cantidad real procesada. Si un trabajo falló sin `requestId` (timeout en generar), busca los asientos huérfanos. **Ejecutarlo apenas termina la corrida:** una corrida posterior con `reemplazar` recrea los asientos con GUID nuevos |

**`reports/index.html` reúne todas las corridas.** Tiene la tabla comparativa y los gráficos de p95 E2E y p95 En Cola por corrida, y es el insumo para el informe final. Se regenera al terminar cada prueba. Para regenerarlo a mano (por ejemplo, después de cambiar el formato):

```powershell
holistor-stress-informe                      # todas las corridas de reports/
holistor-stress-informe reports/<carpeta>    # una corrida (y el índice)
```

### Análisis y hallazgos

- **Cada `reporte.html` y `resumen.md` incluye "Análisis y hallazgos":**
  - Los **hallazgos automáticos** se calculan con reglas sobre los datos de la corrida: resultado, verificación en la base, en qué tramo se va el tiempo, relación con el volumen (correlación), estabilidad en el tiempo, rendimiento, umbrales no cumplidos y servicios lentos.
  - El **análisis escrito** está en `analisis.md`, en la carpeta de la corrida. La primera línea es el resumen que aparece en el índice.
- **`reports/index.html` muestra arriba el análisis general** (`reports/analisis_general.md`), con el resumen de cada corrida en la tabla y sus hallazgos desplegables.
- Después de editar un `analisis.md`, regenerar con `holistor-stress-informe`.

> `reports/` está en `.gitignore`: para conservar los análisis en el repositorio, versionar esos `.md` o copiarlos al informe final.

### Verificación en la base (automática)

Al terminar cada corrida con trabajos, el framework se conecta a la base del tenant y ejecuta las consultas de `verificacion.sql`. Para cada trabajo comprueba:

- Los asientos OK en `nuc_AsientosOtrosModulos`.
- Los comprobantes contabilizados con esos GUID, contra los esperados.
- En los trabajos que fallaron sin `requestId`, si el servidor igual creó los asientos (huérfanos).

El resultado queda en `verificacion_resultado.json` y en las secciones "Verificación en la base" de `reporte.html` y `resumen.md`.

Requisitos:

- `pip install -e ".[bd]"` (instala `pyodbc`).
- ODBC Driver 18 for SQL Server.
- La sección `bd:` del YAML del ambiente.
- Estas variables en `.env`: `HOLISTOR_QA_DB_SERVIDOR`, `HOLISTOR_QA_DB_BASE`, `HOLISTOR_QA_DB_USUARIO` y `HOLISTOR_QA_DB_CLAVE` (autenticación de SQL Server).

```powershell
holistor-stress-verificar --probar                 # prueba la conexión, las tablas y los permisos
holistor-stress-verificar reports/<carpeta>        # verifica una corrida a mano (y regenera su informe)
```

La conexión es de **solo consulta**:

- Se rechaza cualquier sentencia que no sea un único `SELECT`.
- Se abre con `ApplicationIntent=ReadOnly` y siempre termina en `rollback`.
- La clave no aparece en los logs.

Igual conviene usar un usuario `db_datareader`. Si la base no responde, la corrida y su informe se generan igual, con una advertencia en `run.log`.

### Volumen de comprobantes por trabajo

`trabajos.csv` incluye dos columnas de volumen:

- `comprobantes_lote`: todos los comprobantes de los meses del trabajo.
- `comprobantes_precheck`: los registros que devolvió el precheck (primer mes o rango completo, según `flujo.precheck`).

`comprobantes_lote` sale de `data/qa/volumen_comprobantes.csv`, que se genera a partir del Excel *Listado de los datos para la carga*. Si el Excel cambia, hay que volver a generarlo:

```powershell
holistor-stress-volumen "D:\Documentos\0577 Gestor de Comprobantes\Sprint 17\Asientos con Postman\Listado de los datos para la carga.xlsx"
holistor-stress-informe --completar-volumen data/qa/volumen_comprobantes.csv   # completa corridas anteriores
```

`reporte.html` incluye la sección **"¿La demora depende del volumen?"**, con dos gráficos de dispersión (tiempo según comprobantes del lote). `resumen.md` incluye una tabla por trabajo ordenada por volumen.

> En Windows, el `--csv` nativo de Locust escribe con encoding cp1252 y **corrompe las filas cuyo nombre lleva `→`** (las métricas E2E). Usá los `locust_*.csv` de la carpeta de la corrida, que se escriben en UTF-8.

## Smoke de contexto (no crea asientos)

```powershell
locust -f locustfiles/smoke_contexto.py --target-env qa --headless -u 2 -r 1 -t 2m
locust -f locustfiles/smoke_contexto.py --target-env qa --headless -u 20 -r 5 -t 5m
```

Cada usuario virtual hace lo siguiente:

1. Toma una fila exclusiva de `users.csv`.
2. Inicia sesión **una sola vez**.
3. Resuelve empresa, ejercicio, período (con `periodoFiscalId`) y origen, y ejecuta el precheck **una vez**.
4. En cada iteración vuelve a abrir la pantalla con el mismo token.

Sirve para verificar un ambiente y para confirmar que, con N usuarios en paralelo, ninguno pierde la sesión.

> ⚠ Mientras corre, no usar los usuarios `GDC1`…`GDC20` en Postman ni en la UI: la sesión única invalidaría sus tokens.

Qué se ve en las estadísticas de Locust:

| Nombre | Qué es |
|---|---|
| `[Auth] Authenticate`, `[GDC] acceso`, `[GDC] periodos`, `[GDC] GetPeriodosFiscales`, `[GDC] origenes`, `[GDC] tipos-comprobante`, `[GDC] precheck-estructura` | Un renglón por servicio |
| `[Flujo] preparar contexto` | Tiempo de abrir la pantalla completa. Si falla, el mensaje dice por qué |
| `[Sesión] re-login por 401` / `[Sesión] sesión invalidada` | El usuario perdió la sesión: ¿se usó en otro lado? |
| `[Setup] sin fila libre` / `[Setup] guardia de producción` | El usuario virtual no pudo arrancar |

Cada falla lleva la etiqueta de la fila, por ejemplo `[GDC1 · E3064 · 202601-202606 · COMPRAS] período … fuera del ejercicio 5`.

Qué hace el usuario virtual según el tipo de falla:

- **Falla de datos** (empresa sin ejercicio, período fuera del ejercicio, lote sin comprobantes, clave rechazada) o **sesión invalidada**: devuelve la fila y se detiene.
- **Falla transitoria** (5xx, timeout): reintenta en la próxima iteración, hasta `flujo.setup_reintentos_max` veces seguidas.

### Probar sin QA: servidor simulado

`tests/servidor_simulado.py` imita los contratos de la colección, incluida la sesión única. Sirve para probar cambios del framework sin tocar QA:

```powershell
python tests/servidor_simulado.py 8089            # en otra terminal
$env:HOLISTOR_QA_CLAVE = "x"
locust -f locustfiles/smoke_contexto.py --host http://127.0.0.1:8089 --headless -u 20 -r 20 -t 30s
```

## Configuración por ambiente

- Cada ambiente es un archivo `environments/<amb>.yaml` y se elige con `--target-env`.
- Cualquier valor del YAML se puede sobrescribir con variables `HOLISTOR__<seccion>__<clave>`. Ejemplo: `HOLISTOR__FLUJO__POLLING__INTERVALO_S=2`.
- La precedencia es: línea de comando > variables de entorno > `.env` > YAML > valores por defecto.

Argumentos que se agregan a Locust (al importar `holistor_stress.core.bootstrap`):

| Argumento | Uso |
|---|---|
| `--target-env` | Ambiente (por defecto `qa`) |
| `--filtro-filas` | Subconjunto de `users.csv`, por ejemplo `"modulo=GDC,tipoLote=VENTAS\|COMPRAS"` |
| `--permitir-produccion` | Habilita correr contra un ambiente marcado como producción |
| `--load-profile` | Perfil de etapas (Fase 4) |
| `--trabajos-por-usuario` | Trabajos por usuario virtual; al completarlos todos, la prueba termina (0 = sin límite) |
| `--carpeta-reportes` | Carpeta de `trabajos.csv` y `run_info.json` (por defecto `reports/<run_id>`) |

## Tests y lint

```powershell
pytest
ruff check src tests
```

## Estructura

```
src/holistor_stress/
  config/   settings (modelo validado) y loader (YAML + .env + variables de entorno)
  data/     FilaCarga, período, lectura de users.csv, validaciones y filtros
  core/     pool exclusivo, guardia de producción, runtime, bootstrap de Locust, run_id,
            HolistorUser (base_user), contexto, errores y métricas propias
  api/      una función por servicio (rutas.py centraliza URLs y nombres "[Grupo] servicio")
  flows/    sesion (login + re-login 401), seleccion (reglas puras + pasos), gdc (precheck + generar),
            contexto, seguimiento (cola), verificacion, trabajo_gdc (un trabajo de punta a punta)
  tasks/    TaskSets: contexto_tasks (reabrir la pantalla), asiento_tasks (generar asiento GDC)
  users/    usuarios virtuales concretos (SmokeContextoUser, AsientoGdcUser)
  reporting/ trabajos (trabajos.csv + control de IDs), salida (CSV, log, historial), resumen (md/json),
             html (reporte.html e index.html), informe (holistor-stress-informe)
  cli.py    holistor-stress-check
locustfiles/    entrypoints (solo imports): smoke_contexto.py, asiento_gdc.py
environments/   un YAML por ambiente (sin secretos)
data/           users.example.csv por ambiente y plantillas SYJ
tests/          tests unitarios (sin servidor) + servidor_simulado.py
```
