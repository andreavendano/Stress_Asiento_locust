"""Sondeo de "importación en curso" (diagnóstico del 409 IMPORT_ALREADY_RUNNING). NO importa nada.

Consulta cada `importacion.intervalo_sondeo_s` el mismo servicio del paso IMPO 02 y deja cada respuesta en
reports/<corrida>/sondeo.csv. Se corre en paralelo con una importación de OTRA fila IMPO:

    locust -f locustfiles/sondeo_importacion.py --target-env qa --headless -u 1 -r 1 -t 10m \
        --filtro-filas "tenancy=GDCpruebasQA7"
"""

from holistor_stress.core import bootstrap  # noqa: F401
from holistor_stress.users.comprobantes_users import SondeoImportacionUser  # noqa: F401
