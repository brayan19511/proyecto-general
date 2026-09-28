"""Errores de negocio de los servicios.

Los servicios no conocen HTTP: lanzan estos errores y main.py los traduce a
una respuesta con su status y el mensaje (pensado para mostrarse al usuario,
sin detalles internos).
"""


class ServiceError(Exception):
    status_code = 400


class InvalidDataError(ServiceError):
    """Datos con formato o valor no admitido."""

    status_code = 422


class NotFoundError(ServiceError):
    """El recurso no existe, no está activo o es de otra empresa (mismo mensaje)."""

    status_code = 404


class ConflictError(ServiceError):
    """La operación choca con el estado actual (duplicado, superposición, falta configuración)."""

    status_code = 409
