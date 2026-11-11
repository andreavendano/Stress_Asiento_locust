"""Importación de comprobantes de compra. ⚠ CREA COMPROBANTES en el período de cada fila.

    # 1 usuario, 1 importación (la prueba termina sola)
    locust -f locustfiles/importacion_compras.py --target-env qa --headless -u 1 -r 1 -t 30m --trabajos-por-usuario 1

    # repetir importaciones durante 30 minutos con todas las filas IMPO
    locust -f locustfiles/importacion_compras.py --target-env qa --headless -u 2 -r 1 -t 30m

Usa las filas `modulo=IMPO` de users.csv (una empresa distinta por fila) y la sección `importacion:` del
ambiente. Pasos y cómo leer el reporte: docs/ESCENARIO_IMPORTACION.md.
"""

from holistor_stress.core import bootstrap  # noqa: F401  (registra argumentos y carga config + datos)
from holistor_stress.core.shapes import *  # noqa: F403  (rampa escalonada si LOAD_SHAPE=steps)
from holistor_stress.users.comprobantes_users import ImportacionComprasUser  # noqa: F401
