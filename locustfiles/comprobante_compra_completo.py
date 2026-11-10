"""Crear comprobante de compra con la navegación completa de la grabación (113 pasos). ⚠ CREA COMPROBANTES.

    locust -f locustfiles/comprobante_compra_completo.py --target-env qa --headless -u 1 -r 1 -t 5m \
        --trabajos-por-usuario 1

Usa las filas `modulo=CPBTE` con `login=plataforma`. Detalle: docs/ESCENARIO_CREAR_COMPROBANTE.md.
"""

from holistor_stress.core import bootstrap  # noqa: F401
from holistor_stress.core.shapes import *  # noqa: F403
from holistor_stress.users.comprobantes_users import ComprobanteCompletoUser  # noqa: F401
