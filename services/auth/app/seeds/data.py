"""Datos iniciales de auth. Solo estructura: ningún secreto aquí.

Cada empresa declara su propia estructura. Para preconfigurar otra empresa,
agrega un elemento a COMPANIES y vuelve a ejecutar POST /seed: lo existente
no se modifica y solo se crea lo nuevo.

Los códigos de áreas, puestos y roles son únicos dentro de cada empresa.
Usa mayúsculas y guion bajo, sin espacios: ADMIN_TI, ADMIN_CONT.

Niveles de administración:
  - Master admin (is_platform_admin): toda la plataforma. Solo lo crea el seed.
  - Admin de empresa: puesto con el rol ADMIN_EMPRESA (permisos de alcance
    company). Puede haber varios: todos los que ocupen ese puesto.
  - Admin de área: puestos con roles de alcance area (ADMIN_TI, ADMIN_CONT).
"""

# Catálogo global de permisos y sus scopes: se define en app/core/permissions.py
# porque también lo usa el cálculo de permisos en cada solicitud.
from app.core.permissions import PERMISSIONS  # noqa: F401

# Todos los permisos del catálogo con alcance company: administra la empresa entera.
COMPANY_ADMIN_PERMISSIONS = [
    ("areas.manage", "company"),
    ("positions.manage", "company"),
    ("roles.manage", "company"),
    ("memberships.manage", "company"),
    ("users.read", "company"),
    ("history.read", "company"),
]

# Catálogo de países (ISO 3166-1 alfa-2). Para admitir otro país basta con
# agregarlo aquí y a DOCUMENT_TYPES; no cambia ningún modelo.
COUNTRIES = [
    {"code": "PE", "name": "Perú"},
    {"code": "CL", "name": "Chile"},
    {"code": "CO", "name": "Colombia"},
    {"code": "EC", "name": "Ecuador"},
    {"code": "BO", "name": "Bolivia"},
    {"code": "AR", "name": "Argentina"},
    {"code": "MX", "name": "México"},
    {"code": "VE", "name": "Venezuela"},
    {"code": "ES", "name": "España"},
    {"code": "US", "name": "Estados Unidos"},
]

# Tipos de documento por país emisor. pattern valida el número normalizado
# (sin espacios, puntos ni guiones, en mayúsculas). Formato válido no
# significa identidad verificada. Categorías: national_identity, residence,
# passport, other.
PASSPORT_PATTERN = r"^[A-Z0-9]{5,15}$"
DOCUMENT_TYPES = [
    {"country": "PE", "code": "DNI", "name": "Documento Nacional de Identidad", "category": "national_identity", "pattern": r"^\d{8}$"},
    {"country": "PE", "code": "CE", "name": "Carné de Extranjería", "category": "residence", "pattern": r"^[A-Z0-9]{8,12}$"},
    {"country": "CL", "code": "RUT", "name": "Rol Único Tributario / RUN", "category": "national_identity", "pattern": r"^\d{7,8}[0-9K]$"},
    {"country": "CO", "code": "CC", "name": "Cédula de Ciudadanía", "category": "national_identity", "pattern": r"^\d{6,10}$"},
    {"country": "EC", "code": "CI", "name": "Cédula de Identidad", "category": "national_identity", "pattern": r"^\d{10}$"},
    {"country": "ES", "code": "DNI", "name": "Documento Nacional de Identidad", "category": "national_identity", "pattern": r"^\d{8}[A-Z]$"},
    {"country": "ES", "code": "NIE", "name": "Número de Identidad de Extranjero", "category": "residence", "pattern": r"^[XYZ]\d{7}[A-Z]$"},
] + [
    # Un pasaporte por país emisor: el país que lo emite importa.
    {"country": c["code"], "code": "PASAPORTE", "name": "Pasaporte", "category": "passport", "pattern": PASSPORT_PATTERN}
    for c in COUNTRIES
]

COMPANIES = [
    {
        "code": "RASH",
        "name": "RASH PERU SRL",
        "areas": [
            # Todo puesto pertenece a un área; el de admin de empresa va en
            # Gerencia, pero sus permisos valen en toda la empresa.
            {"code": "GER", "name": "Gerencia"},
            {"code": "TI", "name": "Tecnología"},
            {"code": "CONT", "name": "CONTABILIDAD"},
        ],
        # Cada puesto indica a qué área de esta empresa pertenece.
        "positions": [
            {"code": "ADMIN_EMPRESA", "name": "Administrador de la empresa", "area_code": "GER"},
            {"code": "ADMIN_TI", "name": "Administrador de TI", "area_code": "TI"},
            {
                "code": "ADMIN_CONT",
                "name": "Administrador de Contabilidad",
                "area_code": "CONT",
            },
        ],
        "roles": [
            {"code": "ADMIN_EMPRESA", "name": "Administrador de la empresa"},
            {"code": "ADMIN_TI", "name": "Administrador de TI"},
            {"code": "ADMIN_CONT", "name": "Administrador de Contabilidad"},
        ],
        # Permisos de cada rol: código de rol → [(permiso, scope)].
        # Con scope "area", el área es la del puesto que tiene el rol.
        # Los admins de área gestionan lo que hay dentro de su área (puestos y
        # miembros), no el área en sí: areas.manage es solo de alcance company.
        "role_permissions": {
            "ADMIN_EMPRESA": COMPANY_ADMIN_PERMISSIONS,
            "ADMIN_TI": [
                ("positions.manage", "area"),
                ("memberships.manage", "area"),
                ("users.read", "area"),
            ],
            "ADMIN_CONT": [
                ("positions.manage", "area"),
                ("memberships.manage", "area"),
                ("users.read", "area"),
            ],
        },
        "position_roles": {
            "ADMIN_EMPRESA": ["ADMIN_EMPRESA"],
            "ADMIN_TI": ["ADMIN_TI"],
            "ADMIN_CONT": ["ADMIN_CONT"],
        },
        # Puesto que recibe el admin del .env en esta empresa, o None.
        # El admin del seed es master (is_platform_admin) y ya accede a todas
        # las empresas; un puesto solo sirve para que figure como miembro en /me.
        "admin_position_code": None,
    },
]
