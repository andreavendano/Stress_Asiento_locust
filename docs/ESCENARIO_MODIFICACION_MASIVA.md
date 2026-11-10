# Escenario: modificación masiva de cabecera (compras)

Locustfile: [`locustfiles/modificacion_masiva.py`](../locustfiles/modificacion_masiva.py) · Flujo: [`flows/modificacion.py`](../src/holistor_stress/flows/modificacion.py)

> Migrado de `stress_test/tasks/gdc_modificacion_masiva.py` (grabación `gdccomprobantesmodificar-JMeter.json`).
> Mismos pasos y nombres (`MODIF 00` … `MODIF 07`).

En la grilla *Comprobantes > Compras* se seleccionan comprobantes del período, se abre **Modificación masiva** y se
cambian la **Condición fiscal** y la **Provincia**. Después se verifica en la grilla que quedaron con los valores nuevos.

⚠ **Modifica datos**: cambia la cabecera de comprobantes reales del período. Solo QA o ambientes de prueba.

## Cómo correr

```powershell
# Un ciclo por fila (antes SCENARIO=gdc_modificacion_masiva)
locust -f locustfiles/modificacion_masiva.py --target-env qa --headless -u 2 -r 1 -t 10m --trabajos-por-usuario 1

# Repetir (antes SCENARIO=gdc_modificacion_masiva_loop)
locust -f locustfiles/modificacion_masiva.py --target-env qa --headless -u 2 -r 1 -t 10m
```

Cada usuario virtual usa una fila `modulo=MODIF` de `data/qa/users.csv`, con su empresa y su período (un mes). El período
tiene que tener comprobantes de compra, por ejemplo los que deja la importación.

## Pasos de cada ciclo

| Paso | Qué hace |
|---|---|
| `MODIF 01 Comprobantes del periodo` | Lee la grilla de compras del período: ids y valores actuales |
| `MODIF 02 Periodo protegido` | El período fiscal no debe estar protegido |
| `MODIF 03 Seleccion protegida` | Ningún comprobante seleccionado puede estar en un período protegido |
| `MODIF 04 Condiciones IVA` | Catálogo del diálogo; valida los códigos configurados |
| `MODIF 05 Provincias` | Catálogo del diálogo; valida los códigos configurados |
| `MODIF 06 Modificar cabecera` | `modificacion-masiva/cabecera`. Es **sincrónico** |
| `MODIF 07 Verificacion` | Relee la misma página de la grilla y compara por id |
| **`MODIF 00 Modificacion completa (punta a punta)`** | El ciclo entero. Si falla cualquier paso, queda en ERROR con el motivo |

## Configuración (`environments/qa.yaml`, sección `modificacion:`)

| Clave | Antes | Default | Qué controla |
|---|---|---|---|
| `seleccion` | `MODIF_SELECCION` | `lote` | `lote`: `lote_n` comprobantes de una página al azar. `todos`: **todo el período** (`ccpraIds=[]` + `isExclude=true`), pesado con miles de comprobantes |
| `lote_n` | `MODIF_LOTE_N` | `50` | Comprobantes por ciclo en modo `lote` (máximo 100) |
| `cond_fiscal` | `MODIF_COND_FISCAL` | `[4, 1]` | Cada ciclo usa el primero **distinto** del valor actual |
| `provincia` | `MODIF_PROVINCIA` | `[18, 1]` | Misma regla |

## Cómo leer el reporte

- **Statistics**: una fila por paso. `MODIF 00` muestra los ciclos completos y su duración total.
- **Failures**: el motivo que devolvió el servidor, más dos filas propias (tipo `VALIDACION`):
  `MODIF 07 Comprobantes sin modificar` y `MODIF 07 Cantidad de comprobantes`.
- **`run.log`**: bloque `[MODIF RESUMEN]` por ciclo; **`ciclos.csv`**: una fila por ciclo.

## Corrección respecto del original

`MODIF 07` releía la página con `limit = cantidad de comprobantes leídos`. Si la página al azar era la **última e
incompleta** (por ejemplo, 15 comprobantes en la página 3 de 50), la relectura caía en otra ventana de la grilla y el
ciclo fallaba con *"ningún comprobante seleccionado aparece al releer"*. Ahora relee con el mismo tamaño de página del
paso 01 (test `test_modificacion_ultima_pagina_incompleta`).
