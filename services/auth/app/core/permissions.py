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
    # Servicio libro-mayor (services/libro-mayor). Cada nivel incluye al anterior
    # (lo aplica libro-mayor): view consulta; update además modifica reglas y
    # categorías; admin además cuentas y sincronización manual. view admite area
    # para cuando exista la homologación de centros de costo (hoy libro-mayor
    # exige company).
    "ledger.view": ["company", "area"],
    "ledger.update": ["company"],
    "ledger.admin": ["company"],
    # Servicio notificaciones (services/notificaciones). Cada nivel incluye al
    # anterior (lo aplica notificaciones): view consulta envíos; send además los
    # crea; retry además reprocesa y cancela; admin además cuentas SMTP y detalle
    # técnico. own: solo los envíos que solicitó el usuario.
    "notifications.view": ["company", "own"],
    "notifications.send": ["company", "own"],
    "notifications.retry": ["company", "own"],
    "notifications.admin": ["company"],
    # Servicio pagos-proveedores (services/pagos-proveedores). Los aplica ese
    # servicio: view consulta proveedores y lotes; providers.manage además edita
    # el maestro de proveedores; send además crea lotes y envía. Esas dos ramas no
    # se incluyen entre sí. admin incluye todo.
    "payments.view": ["company"],
    "payments.providers.manage": ["company"],
    "payments.send": ["company"],
    "payments.admin": ["company"],
}
