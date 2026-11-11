"""Crear comprobante de compra, solo los requests imprescindibles (~7 por ciclo). ⚠ CREA COMPROBANTES.

    locust -f locustfiles/comprobante_compra_lite.py --target-env qa --headless -u 1 -r 1 -t 5m --trabajos-por-usuario 1
    locust -f locustfiles/comprobante_compra_lite.py --target-env qa --headless -u 2 -r 1 -t 10m

Usa las filas `modulo=CPBTE` de users.csv. Detalle: docs/ESCENARIO_CREAR_COMPROBANTE.md.
"""

from holistor_stress.core import bootstrap  # noqa: F401
from holistor_stress.core.shapes import *  # noqa: F403
from holistor_stress.users.comprobantes_users import ComprobanteLiteUser  # noqa: F401
