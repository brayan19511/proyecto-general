"""Qué datos oculta este servicio en sus logs (schema audit).

El paquete platform_audit trae listas por defecto para toda la plataforma
(packages/platform-audit/src/platform_audit/config.py). Aquí se agregan las
propias de la central; no hace falta tocar el paquete.

Mayúsculas y acentos no importan: "Contraseña" = "contrasena" = "CONTRASENA".
"""

from platform_audit.config import DEFAULT_SENSITIVE_KEY_PARTS, DEFAULT_SENSITIVE_KEYS

# Nombres EXACTOS de campos que la central también oculta. La central registra
# los bodies que reenvía, así que incluye los campos que oculta cada servicio
# publicado (auth: services/auth/app/core/audit.py). Al publicar otro servicio,
# agregar aquí los suyos.
EXTRA_SENSITIVE_KEYS: set[str] = {
    # auth
    "seed_token",
    "first_names",
    "last_names",
    "birth_date",
    "pin",
}

# FRAGMENTOS: si el nombre del campo CONTIENE alguno, se oculta. Usa fragmentos
# distintivos: uno corto como "pin" también ocultaría "shipping".
EXTRA_SENSITIVE_KEY_PARTS: set[str] = set()

# Lo que usa AuditConfig en main.py: paquete + servicio.
SENSITIVE_KEYS = DEFAULT_SENSITIVE_KEYS | frozenset(EXTRA_SENSITIVE_KEYS)
SENSITIVE_KEY_PARTS = DEFAULT_SENSITIVE_KEY_PARTS | frozenset(EXTRA_SENSITIVE_KEY_PARTS)
