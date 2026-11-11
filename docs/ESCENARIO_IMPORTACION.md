# Escenario: importación de comprobantes de compra

Locustfile: [`locustfiles/importacion_compras.py`](../locustfiles/importacion_compras.py) · Flujo: [`flows/importacion.py`](../src/holistor_stress/flows/importacion.py)

> Migrado de `stress_test/tasks/gdc_importacion_lite.py`. Los pasos, las validaciones y los nombres de cada fila del
> reporte (`IMPO 00` … `IMPO 15`) son los mismos, para poder comparar corridas viejas y nuevas.

## Qué prueba

Cada usuario virtual hace lo mismo que una persona en la pantalla **Importar** de Gestor de Comprobantes:

1. arma un archivo CSV con comprobantes de compra (formato *Portal IVA* de ARCA),
2. lo sube y lo valida,
3. lanza la importación definitiva,
4. espera a que termine,
5. **verifica que los comprobantes quedaron creados**.

Si un paso falla o la importación no se completa, el ciclo queda en **ERROR**, con el motivo, en el reporte y en `ciclos.csv`.

## Antes de correr

**Un usuario y una empresa por usuario virtual.** La plataforma tiene dos límites:

- una sola sesión activa por usuario: si dos usuarios virtuales usan la misma cuenta, el segundo login invalida el
  token del primero;
- una sola importación a la vez por empresa.

Cada fila `modulo=IMPO` de `data/qa/users.csv` es un usuario virtual con su empresa y su período:

```
id,activo,tenantId,usuario,clave,modulo,empresa,periodo,tipoLote,reemplazar,plantilla,login,tenancy
T867-E6-IMPO-202601,true,867,admin,<clave>,IMPO,6,202601,,,,plataforma,GDCpruebasQA7
T866-E6-IMPO-202601,true,866,admin,<clave>,IMPO,6,202601,,,,plataforma,GDCpruebasQA6
```

- `login=plataforma` + `tenancy`: login de la plataforma SaaS (IsTenantAvailable + TokenAuth), como el `user.py` original.
- `periodo`: un único mes (AAAAMM).
- Si dos filas IMPO del mismo tenant tienen la misma empresa, la prueba **no arranca** y el mensaje dice qué filas
  corregir (también lo avisa `holistor-stress-check`).
- La cantidad de usuarios (`-u`) no puede superar la cantidad de filas IMPO.
- La empresa debe tener el período creado, al menos un proveedor y el origen de importación configurado.

## Configuración (`environments/qa.yaml`, sección `importacion:`)

Reemplaza a las variables `IMPO_*` del `.env`. Cualquier valor se puede pisar con `HOLISTOR__IMPORTACION__<CLAVE>`,
por ejemplo `HOLISTOR__IMPORTACION__LOTE_N=10000`.

| Clave | Antes | Qué es |
|---|---|---|
| `origen_codigo` | `IMPO_ORIGEN_CODIGO` | Código del origen de importación (`PIC` = Portal IVA). El id se busca en la API |
| `tipo_comprobante` | `IMPO_TIPO_COMPROBANTE` | Código ARCA del tipo de comprobante del CSV (`11` = Factura C) |
| `moneda` / `tipo_cambio` | `IMPO_MONEDA` / `IMPO_TIPO_CAMBIO` | Moneda y tipo de cambio |
| `importe_min` / `importe_max` | `IMPO_IMPORTE_MIN` / `_MAX` | Rango del importe total de cada comprobante (aleatorio) |
| `lote_n` (28) | `IMPO_LOTE_N` | Comprobantes por archivo |
| `espera_empresa_libre_s` (600) | `IMPO_ESPERA_EMPRESA_LIBRE_SEG` | Cuánto esperar si la empresa tiene otra importación en curso |
| `timeout_proceso_archivo_s` (3600) | `IMPO_TIMEOUT_PROCESO_ARCHIVO_SEG` | Máximo para que el back procese el archivo |
| `timeout_job_s` (3600) | `IMPO_TIMEOUT_JOB_SEG` | Máximo para que termine la importación definitiva |
| `intervalo_sondeo_s` (5) | `IMPO_INTERVALO_SONDEO_SEG` | Cada cuánto se consulta un estado |
| `tam_pagina` (100) | `IMPO_TAM_PAGINA` | Página de `GetListComprobantes` (máximo 100) |
| — | `IMPO_TIMEOUT_REQUEST_SEG` | Ahora es el general `timeout_request_s` del ambiente (300 en QA) |

**De dónde sale cada dato** (no hay valores fijos en el código):

| Dato | Origen |
|---|---|
| Token, tenant, userId | Login de cada usuario virtual |
| Empresa, período | Columnas `empresa` / `periodo` de la fila → id real por API |
| Proveedor del CSV (CUIT, razón social, tipo doc.) | Primer proveedor activo de la empresa (API) |
| Origen, nombre del archivo, delimitador | `GdcImpoOrigen/GetListForImport` según `origen_codigo` |
| Columnas del CSV | Encabezado de `data/plantillas/importacion/plantilla_importacion_compras_oficial.csv`, por nombre |
| Punto de venta / número | Aleatorio por usuario + correlativo por ciclo (sin duplicados entre ciclos) |
| idArchivo, líneas, jobId | Respuestas de la API en cada ciclo |

## Cómo correr

```powershell
# Una importación por fila (antes SCENARIO=gdc_importacion_lite): la prueba termina sola
locust -f locustfiles/importacion_compras.py --target-env qa --headless -u 2 -r 1 -t 60m --trabajos-por-usuario 1

# Importaciones repetidas durante 30 minutos (antes SCENARIO=gdc_importacion_lite_loop)
locust -f locustfiles/importacion_compras.py --target-env qa --headless -u 2 -r 1 -t 30m
```

La salida queda en `reports/<run_id>_importacion_compras_<N>u/` (ver el README: `reporte.html`, `ciclos.csv`, `run.log`…).

## Pasos del ciclo y cómo leer el reporte

| Fila | Qué hace | Falla si… |
|---|---|---|
| `IMPO 00 Importacion completa (punta a punta)` | El ciclo entero (tipo `FLUJO`). **Es la fila principal** | Falló cualquier paso (motivo en Failures) |
| `IMPO 01 Origen de importacion` | Busca el origen por código (una vez por usuario) | No existe el origen en la empresa (lista los disponibles) |
| `IMPO 02 Empresa libre` | Espera que la empresa no tenga otra importación en curso | Sigue ocupada después de `espera_empresa_libre_s` |
| `IMPO 03 Comprobantes antes` | Cuenta comprobantes del período | Error HTTP |
| `IMPO 04 Subir archivo` | `SelectFile` (multipart) | No devuelve `fileTempId` |
| `IMPO 05 Validacion preliminar` | Estructura, nombre, encabezado | `canProceed=false` o alguna validación en falso |
| `IMPO 06 Incorporar archivo` | Registra el archivo | No devuelve `idArchivo` |
| `IMPO 07 Procesamiento del archivo` | Espera que se procesen las líneas | Error del archivo o no termina a tiempo |
| `IMPO 08 Resumen del archivo` | Totales de líneas OK / advertencia / error | Error HTTP |
| `IMPO 09 Lineas del archivo` | Toma **solo** las líneas de este archivo y agrupa las rechazadas por motivo | Ninguna línea importable |
| `IMPO 10 Iniciar importacion` | `ImportacionDefinitiva/Iniciar` | Error HTTP o `success=false` |
| `IMPO 11 Validar definitivos` | Validación final | Ningún comprobante válido |
| `IMPO 12 Cuota` | Cuota de comprobantes del tenant | Cuota excedida |
| `IMPO 13 Lanzar importacion` | `ImportacionDefinitiva/Start` | No devuelve `jobId` |
| `IMPO 14 Seguimiento del job` | Stream de estado del job (front, cookie `auth_token`) | Ver abajo |
| `IMPO 15 Comprobantes despues` | Cuenta de nuevo y compara | Se crearon menos de los aceptados |

Además se registran como filas propias (tipo `VALIDACION`) los problemas de negocio, aunque el ciclo siga:
`IMPO 09 Lineas rechazadas por el backend`, `IMPO 11 Comprobantes rechazados`, `IMPO 14 Job no termino`,
`IMPO 14 Job con errores` e `IMPO 15 Comprobantes despues`.

Cada falla lleva la etiqueta de la fila, por ejemplo `[admin@GDCpruebasQA7 · E6 · 202601 · IMPO] IMPO 04 Subir archivo: HTTP 500 …`.

Al terminar cada ciclo se escribe en `run.log` un bloque `[IMPO RESUMEN]` (igual que antes) y una fila en `ciclos.csv`
con los mismos datos en la columna `detalle`.

## Diagnóstico: sondeo de "importación en curso"

[`locustfiles/sondeo_importacion.py`](../locustfiles/sondeo_importacion.py) (antes `scripts/sondeo_estado_empresa.py`)
consulta cada `intervalo_sondeo_s` el servicio del paso `IMPO 02` y deja cada respuesta en `sondeo.csv`. No importa
nada. Se corre en paralelo con una importación de **otra** fila:

```powershell
locust -f locustfiles/sondeo_importacion.py --target-env qa --headless -u 1 -r 1 -t 10m --filtro-filas "tenancy=GDCpruebasQA7"
```

## Errores frecuentes

| Mensaje | Causa | Qué hacer |
|---|---|---|
| `las N filas están en uso` | Más usuarios que filas IMPO | Bajar `-u` o agregar filas |
| `importan en la misma empresa` | Dos filas IMPO del mismo tenant con la misma empresa | Una empresa distinta por fila |
| `falta la sección 'importacion:'` | El ambiente no tiene la configuración | Completarla en `environments/<amb>.yaml` |
| `IMPO 02 … sigue con otra importación en curso` | La empresa quedó con una importación abierta | Esperar o usar otra empresa |
| `IMPO 01 … no existe el origen` | El origen no está activo en esa empresa | Activarlo o cambiar `origen_codigo` |
| `Tipo Movimiento o Concepto no Gravado o Exento no relacionado…` | La empresa no tiene el tipo de movimiento por omisión para compras | Configurarlo en GdC o usar otra empresa |
| `[Sesión] sesión invalidada` | Dos sesiones con la misma cuenta | Una cuenta por usuario virtual, y no usarla en la UI mientras corre |
