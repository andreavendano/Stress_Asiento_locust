"""Guardia de producción: la carga crea asientos reales (y con reemplazar borra los existentes)."""

from __future__ import annotations

from holistor_stress.config.settings import Settings


class GuardiaProduccionError(Exception):
    pass


def es_produccion(settings: Settings, url: str | None = None) -> bool:
    url = (url or settings.base_url).rstrip("/").lower()
    return settings.es_produccion or any(
        u.strip() and url.startswith(u.strip().rstrip("/").lower()) for u in settings.urls_produccion
    )


def verificar_ambiente(settings: Settings, url_efectiva: str | None = None, permitir_produccion: bool = False):
    url = url_efectiva or settings.base_url
    if es_produccion(settings, url) and not permitir_produccion:
        raise GuardiaProduccionError(
            f"{url} es PRODUCCIÓN (ambiente '{settings.nombre}'): la carga crea asientos reales. "
            "Usar el ambiente de QA o, conscientemente, --permitir-produccion."
        )
