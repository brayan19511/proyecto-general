"""Errores de negocio del servicio.

Los servicios y repositorios no conocen HTTP: lanzan estos errores y main.py
los traduce a una respuesta con su status y el mensaje (pensado para mostrarse
al usuario, sin detalles internos).
"""


class ServiceError(Exception):
    status_code = 400


class InvalidDataError(ServiceError):
    """Datos con formato o valor no admitido."""

    status_code = 422


class NotFoundError(ServiceError):
    """El recurso no existe o no es de esta empresa (mismo mensaje)."""

    status_code = 404


class ConflictError(ServiceError):
    """La operación choca con el estado actual o falta configuración."""

    status_code = 409


class UpstreamError(ServiceError):
    """Una base externa (Ofisis) falló (mensaje seguro, sin detalles internos)."""

    status_code = 502


class DeadlineExceededError(ServiceError):
    """Una base externa tardó demasiado o tenía los datos bloqueados."""

    status_code = 504
