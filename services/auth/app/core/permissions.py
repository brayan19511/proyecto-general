"""Catálogo de permisos de auth: código → scopes que admite.

Un permiso representa una capacidad que existe en el código: agregar un código
aquí no crea la función. Por eso no hay CRUD de permisos; el seed carga este
catálogo en la tabla permissions.

Lo usan dos lugares:
  - El seed, para rechazar un rol-permiso con un scope no admitido.
  - AccessService, que ignora en cada solicitud cualquier rol-permiso cuyo
    scope ya no se admita (por ejemplo, si el catálogo se restringe después).

Scopes:
  company → toda la empresa activa.
  area    → solo el área del puesto que concede el permiso.
  own     → solo recursos propios del usuario.
"""

PERMISSIONS: dict[str, list[str]] = {
    # Crear, renombrar y dar de baja áreas: decisión de la empresa, no de un
    # admin de área (que gestiona lo que hay dentro de su área).
    "areas.manage": ["company"],
    "positions.manage": ["company", "area"],
    "roles.manage": ["company"],  # Los roles son de la empresa, no de un área.
    "memberships.manage": ["company", "area"],
    "users.read": ["company", "area"],
    # Consultar el historial de cambios de la empresa (GET /history).
    "history.read": ["company"],
}
