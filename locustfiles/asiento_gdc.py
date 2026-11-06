"""Generar Asiento GDC de punta a punta. ⚠ CREA ASIENTOS en el ambiente (y con reemplazar=true borra los previos).

    # 1 usuario, 1 trabajo (la prueba termina sola)
    locust -f locustfiles/asiento_gdc.py --target-env qa --headless -u 1 -r 1 -t 20m --trabajos-por-usuario 1

    # carga: 20 usuarios durante 30 minutos
    locust -f locustfiles/asiento_gdc.py --target-env qa --headless -u 20 -r 2 -t 30m

Cada usuario virtual toma una fila exclusiva de users.csv, prepara el contexto y en cada iteración
genera el asiento, sigue la cola hasta Finalizado, verifica el destino y registra el trabajo en
reports/<run_id>_asiento_gdc_<N>u/ (reporte.html, resumen.md, trabajos.csv…).
"""

from holistor_stress.core import bootstrap  # noqa: F401  (registra argumentos y carga config + datos)
from holistor_stress.users.asiento_users import AsientoGdcUser  # noqa: F401
