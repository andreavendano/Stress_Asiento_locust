# Escenario: crear comprobante de compra (lite y completo)

Flujo: [`flows/comprobante.py`](../src/holistor_stress/flows/comprobante.py) · Pasos del completo: [`flows/pasos_comprobante_completo.py`](../src/holistor_stress/flows/pasos_comprobante_completo.py)

⚠ **Crea comprobantes reales** en el período de cada fila.

| Locustfile | Antes | Requests por ciclo |
|---|---|---|
| [`comprobante_compra_lite.py`](../locustfiles/comprobante_compra_lite.py) | `SCENARIO=gdc_nuevo_lite` (`tasks/gdc_lite.py`) | ~7: 4 lookups, crear y 2 lecturas del detalle |
| [`comprobante_compra_completo.py`](../locustfiles/comprobante_compra_completo.py) | `SCENARIO=gdc_nuevo` (`tasks/gdc.py`) | 112: la navegación completa de la grabación de BlazeMeter |

Los dos usan las filas `modulo=CPBTE` de `data/qa/users.csv` (un mes por fila). El **completo** además navega la
plataforma (portal, banners, suscripciones, dashboard del front), así que necesita `login=plataforma`.

```powershell
locust -f locustfiles/comprobante_compra_lite.py --target-env qa --headless -u 2 -r 1 -t 10m --trabajos-por-usuario 1
locust -f locustfiles/comprobante_compra_completo.py --target-env qa --headless -u 1 -r 1 -t 10m --trabajos-por-usuario 1
```

Sin `--trabajos-por-usuario` repiten hasta que termina la prueba (antes `*_loop`).

## Qué hace cada ciclo

**Lite** (los nombres de las filas son los de antes):

| Fila | Qué hace |
|---|---|
| `/LITE/Lookups/GetAlicuotasVigentes`, `…GdcClienteProveedor_Buscar`, `…GetClasificacionARCA`, `…getMovimientoTipoConsultaLookup_GRC` | Lookups que la pantalla usa para armar el comprobante |
| `/LITE/ComprobantesCompra/CREAR_(CORE)` | Crea el comprobante |
| `/LITE/ComprobantesCompra/GetById_DETALLE_1` y `_2` | Lee el detalle del comprobante recién creado (solo si se creó) |
| `CPBTE 00 Comprobante lite (punta a punta)` | **Nuevo**: el ciclo entero (tipo `FLUJO`). Falla si no se crea o no se puede leer |

**Completo**: los pasos 1 a 113 de `tasks/gdc.py`, con los mismos métodos, URLs, nombres, headers y bodies (la tabla
se generó a partir del archivo original). El paso 103 crea el comprobante y 108/109 abren su detalle. Los pasos de
navegación no cortan el ciclo, como en el navegador; solo se marcan como falla si responden ≥ 400. La fila
`CPBTE 00 Comprobante completo (punta a punta)` es nueva.

## Datos

Empresa, período, proveedor y dos tipos de movimiento gravados de compras salen de la API con el token del propio
usuario (`flows/maestros.py`, antes `BaseTaskSet._lookup_master_data`). Con `maestros.cache: true` (antes
`CACHE_LOOKUPS=1`) los resuelve el primer usuario de cada tenant/empresa/período y el resto los reutiliza.

Cada comprobante lleva entropía para no chocar con el control de duplicados (`DUPLICATE_VOUCHER`): día del mes, hora,
punto de venta, tipo de comprobante, importes y concepto, con los mismos rangos que antes para cada variante. Si el
back responde `saved=false` o `duplicateWarning`, el request y el ciclo quedan en falla con el código.
