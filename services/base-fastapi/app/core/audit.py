"""Qué datos oculta este servicio en sus logs (schema audit).

El paquete platform_audit trae listas por defecto para toda la plataforma
(packages/platform-audit/src/platform_audit/config.py). Aquí se agregan las
propias del servicio; no hace falta tocar el paquete.

Mayúsculas y acentos no importan: "Contraseña" = "contrasena" = "CONTRASENA".
"""

from platform_audit.config import DEFAULT_SENSITIVE_KEY_PARTS, DEFAULT_SENSITIVE_KEYS

# Nombres EXACTOS de campos que el servicio también oculta. Ejemplo: {"pin"}
EXTRA_SENSITIVE_KEYS: set[str] = set()

# FRAGMENTOS: si el nombre del campo CONTIENE alguno, se oculta. Usa fragmentos
# distintivos: uno corto como "pin" también ocultaría "shipping".
EXTRA_SENSITIVE_KEY_PARTS: set[str] = set()

# Lo que usa AuditConfig en main.py: paquete + servicio.
SENSITIVE_KEYS = DEFAULT_SENSITIVE_KEYS | frozenset(EXTRA_SENSITIVE_KEYS)
SENSITIVE_KEY_PARTS = DEFAULT_SENSITIVE_KEY_PARTS | frozenset(EXTRA_SENSITIVE_KEY_PARTS)
