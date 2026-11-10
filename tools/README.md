# Herramientas sueltas (migradas de stress_test/scripts)

No son escenarios de Locust: son utilidades que se corren a mano.

| Archivo | Qué hace |
|---|---|
| `har_to_locust.py` | Convierte una grabación `.har` (Chrome DevTools / BlazeMeter) en un `locustfile.py` de arranque |
| `blazemeter_json_to_locust.py` | Lo mismo, a partir del JSON que exporta BlazeMeter |
| `generar_lote_20k.py` | Arma y sube UN archivo de 20.000 comprobantes de compra (enero 2026, empresa 6, QA7) |
| `importar_definitivo_20k.py` | Importación definitiva de ese lote por bloques de 10.000 ids (el back rechaza bodies de más de ~100 KB) |

`generar_lote_20k.py` e `importar_definitivo_20k.py` tienen fijos el tenant QA7, la empresa 6 y el período 151 (01/2026),
igual que antes. La cuenta ya no sale de `accounts/accounts_QA.csv`: usan la primera fila `modulo=IMPO` con
`login=plataforma` de `data/qa/users.csv` (`tools/_cuenta.py`).

```powershell
python tools/har_to_locust.py ruta\grabacion.har
python tools/generar_lote_20k.py
python tools/importar_definitivo_20k.py
```

> Para la carga real de importación conviene el escenario `locustfiles/importacion_compras.py`: con
> `HOLISTOR__IMPORTACION__LOTE_N=10000` cada ciclo importa un archivo de 10.000 comprobantes.
