from dataclasses import dataclass, field

from sqlalchemy.engine import Engine

from platform_audit.proxies import Networks, parse_trusted
from platform_audit.redact import Masker

# ---------------------------------------------------------------------------
# Datos sensibles: se guardan como "***" en bodies, parámetros y headers.
#
# Son los valores POR DEFECTO de todos los servicios. Para cambiarlos:
#   - para toda la plataforma: edita estas constantes (aquí, en el paquete);
#   - solo para un servicio: pásale sus listas a AuditConfig (ver README),
#     sumándolas a estas o reemplazándolas.
# Mayúsculas y acentos no importan: "Contraseña" = "contrasena".
# ---------------------------------------------------------------------------

# Nombres EXACTOS de campos sensibles.
DEFAULT_SENSITIVE_KEYS = frozenset(
    {
        "key",
        "api_key",
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-seed-token",
        "email",
        "correo",
        "admin_email",
        "document_number",
        "numero_documento",
        "dni",
        "rut",
        "pasaporte",
        "passport",
    }
)

# FRAGMENTOS: si el nombre del campo CONTIENE alguno, se oculta.
# "password" oculta password, new_password, passwordHash, user_password...
DEFAULT_SENSITIVE_KEY_PARTS = frozenset(
    {
        "password",
        "passwd",
        "contrasena",  # También cubre "contraseña": se comparan sin acentos.
        "clave",
        "token",
        "secret",
        "secreto",
        "credential",
        "credencial",
    }
)

# Headers que se guardan. Lista positiva: todo lo demás se descarta.
DEFAULT_ALLOWED_HEADERS = frozenset(
    {
        "user-agent",
        "content-type",
        "content-length",
        "accept",
        "origin",
        "referer",
        "x-company-id",
        "x-trace-id",
        "x-parent-operation-id",
        "x-forwarded-for",
    }
)

# Máximo de body guardado por solicitud (bytes). Más grande: solo tipo y tamaño.
DEFAULT_MAX_BODY_BYTES = 4096


@dataclass(frozen=True)
class AuditConfig:
    """Configuración de un servicio que usa platform_audit.

    - engine: el del servicio. Los logs usan conexiones propias, fuera de la
      transacción de negocio: si fallan, la operación de negocio no se deshace.
    - trusted_proxies: IPs exactas ("10.0.0.5") o rangos CIDR ("172.30.0.0/24")
      desde los que se aceptan X-Trace-Id, X-Parent-Operation-Id y
      X-Forwarded-For (ver proxies.py). De cualquier otra conexión se
      ignoran: la correlación nunca equivale a autorización.
    - sensitive_keys / sensitive_key_parts: qué se oculta (por defecto, las
      constantes de arriba).
    """

    engine: Engine
    service: str
    service_version: str
    enabled: bool = True
    trusted_proxies: frozenset[str] = frozenset()
    exclude_paths: frozenset[str] = frozenset({"/docs", "/redoc", "/openapi.json", "/health", "/ready"})
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    sensitive_keys: frozenset[str] = field(default=DEFAULT_SENSITIVE_KEYS)
    sensitive_key_parts: frozenset[str] = field(default=DEFAULT_SENSITIVE_KEY_PARTS)
    allowed_headers: frozenset[str] = field(default=DEFAULT_ALLOWED_HEADERS)
    # Se calcula una vez a partir de las dos listas (normalizadas).
    masker: Masker = field(init=False, repr=False, compare=False)
    trusted_networks: Networks = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        # Un valor inválido en trusted_proxies falla aquí, al arrancar.
        object.__setattr__(self, "trusted_networks", parse_trusted(self.trusted_proxies))
        object.__setattr__(
            self, "masker", Masker.from_lists(self.sensitive_keys, self.sensitive_key_parts)
        )
