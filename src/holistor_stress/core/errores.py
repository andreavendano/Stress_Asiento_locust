"""Fallas de los pasos del flujo. Los mensajes ya llevan la etiqueta de la fila y nunca la clave.

La jerarquía decide qué hace el usuario virtual:

- `FallaDatos`: la fila no puede trabajar en este ambiente (empresa sin ejercicio, período fuera
  del ejercicio, lote sin comprobantes, credenciales rechazadas). Reintentar no sirve: el usuario
  virtual devuelve la fila y se detiene, para no martillar el servidor con una fila inválida.
- `FallaHttp`: error del servidor o de red (5xx, timeout, respuesta inesperada). Puede ser
  transitorio, sobre todo bajo stress: se reintenta en la próxima iteración, con un tope.
- `NoAutorizadoError`: 401 en un servicio autenticado. Lo maneja `flows.sesion` con un re-login.
- `SesionInvalidadaError`: el re-login no alcanzó (¿el usuario se usó en otra sesión?). Se detiene.
- `FallaTrabajo`: el asiento no terminó bien. Se registra y se sigue con el próximo trabajo.
"""

from __future__ import annotations


class FallaPaso(Exception):
    """Falla de un paso del flujo, con un mensaje listo para mostrar."""


class FallaDatos(FallaPaso):
    pass


class FallaHttp(FallaPaso):
    def __init__(self, mensaje: str, status: int | None = None):
        super().__init__(mensaje)
        self.status = status  # código HTTP; None o 0 = sin respuesta


class NoAutorizadoError(FallaHttp):
    pass


class SesionInvalidadaError(FallaPaso):
    pass


class FallaTrabajo(FallaPaso):
    """El trabajo de asiento no cerró (Error en la cola, timeout, requestId perdido, verificación).

    Es la falla que la prueba quiere detectar: se registra y el usuario virtual sigue con el próximo.
    """
