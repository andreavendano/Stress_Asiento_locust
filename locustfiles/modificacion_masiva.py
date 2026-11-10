"""Modificación masiva de cabecera (Condición fiscal y Provincia). ⚠ MODIFICA COMPROBANTES del período.

    locust -f locustfiles/modificacion_masiva.py --target-env qa --headless -u 2 -r 1 -t 10m --trabajos-por-usuario 1

Usa las filas `modulo=MODIF` de users.csv y la sección `modificacion:` del ambiente. El período de cada fila
tiene que tener comprobantes de compra (por ejemplo los que deja la importación).
Detalle: docs/ESCENARIO_MODIFICACION_MASIVA.md.
"""

from holistor_stress.core import bootstrap  # noqa: F401
from holistor_stress.core.shapes import *  # noqa: F403
from holistor_stress.users.comprobantes_users import ModificacionMasivaUser  # noqa: F401
