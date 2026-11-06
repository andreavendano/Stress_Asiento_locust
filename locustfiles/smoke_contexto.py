"""Smoke de contexto: verifica un ambiente SIN crear asientos.

    locust -f locustfiles/smoke_contexto.py --target-env qa --headless -u 2 -r 1 -t 2m

Cada usuario virtual toma una fila exclusiva de users.csv, inicia sesión una vez, resuelve empresa,
ejercicio, período y origen (+ precheck una vez) y después reabre la pantalla en cada iteración.
"""

from holistor_stress.core import bootstrap  # noqa: F401  (registra argumentos y carga config + datos)
from holistor_stress.users.smoke_users import SmokeContextoUser  # noqa: F401
