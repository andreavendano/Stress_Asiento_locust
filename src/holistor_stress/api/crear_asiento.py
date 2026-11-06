"""Servicios de la cola de Crear Asiento (comunes a GDC y SYJ)."""

from __future__ import annotations

from typing import Any

from holistor_stress.api import rutas
from holistor_stress.api.http import UsuarioApi, llamar


def progreso(user: UsuarioApi, request_id: str) -> Any:
    """GET crear-asiento/{requestId}/progreso → {estado: En Cola | En Proceso | Finalizado | Error, …}.

    404 = requestId desconocido (vive 30 min en memoria y se pierde si el servidor se reinicia, R5).
    """
    return llamar(user, "GET", rutas.progreso(request_id), rutas.N_PROGRESO).data


def resultado(user: UsuarioApi, request_id: str) -> Any:
    """GET crear-asiento/{requestId} → {asientos[]: idAsiento, empresa, ejercicio, status, errores}."""
    return llamar(user, "GET", rutas.resultado(request_id), rutas.N_RESULTADO).data
