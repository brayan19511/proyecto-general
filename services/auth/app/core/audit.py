"""Qué datos oculta auth en sus logs (schema audit).

El paquete platform_audit trae listas por defecto para toda la plataforma
(packages/platform-audit/src/platform_audit/config.py). Aquí se agregan las
propias de auth. Para cambiar el comportamiento de auth, edita estas constantes;
no hace falta tocar el paquete ni el resto del código.

Mayúsculas y acentos no importan: "Contraseña" = "contrasena" = "CONTRASENA".
"""

from platform_audit.config import DEFAULT_SENSITIVE_KEY_PARTS, DEFAULT_SENSITIVE_KEYS

# Nombres EXACTOS de campos que auth también oculta, además de los del paquete.
EXTRA_SENSITIVE_KEYS: set[str] = {
    "seed_token",
    "first_names",
    "last_names",
    "birth_date",
    "pin",
}

# FRAGMENTOS: si el nombre del campo CONTIENE alguno, se oculta. Usa
# fragmentos distintivos: uno corto como "pin" también ocultaría "shipping" o
# "spinner". Para palabras cortas, mejor la lista exacta de arriba.
# Ejemplo: {"tarjeta", "cvv"}
EXTRA_SENSITIVE_KEY_PARTS: set[str] = set()

# Lo que usa AuditConfig en main.py: paquete + auth.
# Para REEMPLAZAR en lugar de sumar, asigna aquí directamente tu lista, p. ej.:
#   SENSITIVE_KEY_PARTS = frozenset({"password", "contrasena"})
SENSITIVE_KEYS = DEFAULT_SENSITIVE_KEYS | frozenset(EXTRA_SENSITIVE_KEYS)
SENSITIVE_KEY_PARTS = DEFAULT_SENSITIVE_KEY_PARTS | frozenset(EXTRA_SENSITIVE_KEY_PARTS)
