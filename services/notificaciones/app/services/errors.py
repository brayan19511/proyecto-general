"""Errores de negocio de los servicios.

Los servicios no conocen HTTP: lanzan estos errores y main.py los traduce a
{"detail": mensaje} con su status (formato de la plataforma, acuerdo
2026-10-01). code es opcional: solo cuando el consumidor necesita distinguir
el caso por programa (p. ej. "message_too_large"); extra agrega datos del caso
(p. ej. qué mensaje y cuánto pesa). El mensaje se muestra al usuario, sin
detalles internos.
"""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str, *, code: str | None = None, extra: dict | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


class InvalidDataError(ServiceError):
    """Datos con formato o valor no admitido."""

    status_code = 422


class NotFoundError(ServiceError):
    """El recurso no existe o es de otra empresa (mismo mensaje: no revela cuál)."""

    status_code = 404


class ConflictError(ServiceError):
    """La operación choca con el estado actual (duplicado, estado no válido)."""

    status_code = 409


class GoneError(ServiceError):
    """El recurso existió pero su contenido ya no está (p. ej. adjunto purgado)."""

    status_code = 410
