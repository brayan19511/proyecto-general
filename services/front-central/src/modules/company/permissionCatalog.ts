// Permisos: la lista la da auth (GET /auth/catalog/permissions, fuente
// services/auth/app/core/permissions.py), así se ve siempre todo lo registrado.
// Aquí solo hay textos en español para mostrarlos mejor: un permiso nuevo sin
// texto aparece igual, con su código y agrupado por su prefijo.

export type PermissionScope = 'company' | 'area' | 'own'

// Permiso del catálogo de auth.
export type CatalogPermission = {
  code: string
  scopes: PermissionScope[]
  loaded: boolean // false: está en el código de auth pero falta ejecutar su seed
}

// Lo que muestra la pantalla: el catálogo + sus textos.
export type PermissionInfo = CatalogPermission & {
  group: string
  label: string
  description: string
}

export const SCOPE_LABEL: Record<PermissionScope, string> = {
  company: 'Toda la empresa',
  area: 'Solo su área',
  own: 'Solo lo propio',
}

export const SCOPE_HELP: Record<PermissionScope, string> = {
  company: 'Vale en toda la empresa activa.',
  area: 'Vale solo en el área del puesto que concede el rol.',
  own: 'Vale solo sobre lo que la persona creó o pidió.',
}

// Grupo por prefijo del código ("ledger.view" → Libro mayor).
const GROUPS: Record<string, string> = {
  areas: 'Organización',
  positions: 'Organización',
  roles: 'Organización',
  memberships: 'Organización',
  users: 'Organización',
  history: 'Organización',
  ledger: 'Libro mayor',
  notifications: 'Notificaciones',
  payments: 'Pago a proveedores',
}

const TEXTS: Record<string, { label: string; description: string }> = {
  'areas.manage': { label: 'Gestionar áreas', description: 'Crear, renombrar, dar de baja y restaurar áreas.' },
  'positions.manage': { label: 'Gestionar puestos', description: 'Crear, editar y dar de baja puestos y asignarles roles.' },
  'roles.manage': { label: 'Gestionar roles', description: 'Crear roles y conceder o quitar sus permisos.' },
  'memberships.manage': { label: 'Gestionar miembros', description: 'Agregar, suspender y dar de baja miembros, y asignarles puestos.' },
  'users.read': { label: 'Ver miembros', description: 'Ver la lista de miembros y sus puestos.' },
  'history.read': { label: 'Ver historial', description: 'Ver quién cambió qué en la empresa.' },
  'ledger.view': {
    label: 'Consultar libro mayor',
    description: 'Ver líneas, resumen, consultas en SAP, sincronización y reglas. Con "Solo su área", solo los centros de costo homologados a su área.',
  },
  'ledger.update': { label: 'Editar reglas y categorías', description: 'Incluye consultar. Crear y editar reglas y categorías, y reclasificar.' },
  'ledger.admin': { label: 'Administrar libro mayor', description: 'Incluye lo anterior. Cuentas, sincronización manual y homologación de centros de costo.' },
  'notifications.view': { label: 'Ver envíos de correo', description: 'Ver envíos, sus mensajes y adjuntos. Con "Solo lo propio", solo los que pidió la persona.' },
  'notifications.send': { label: 'Enviar correos', description: 'Incluye ver. Crear envíos de correo.' },
  'notifications.retry': { label: 'Reprocesar envíos', description: 'Incluye enviar. Reintentar o cancelar mensajes fallidos.' },
  'notifications.admin': { label: 'Administrar notificaciones', description: 'Incluye todo lo anterior. Cuentas SMTP, plantillas e intentos técnicos.' },
  'payments.view': { label: 'Ver pagos a proveedores', description: 'Ver proveedores y lotes de pago.' },
  'payments.providers.manage': { label: 'Gestionar proveedores', description: 'Incluye ver. Crear y editar el maestro de proveedores.' },
  'payments.send': { label: 'Enviar pagos', description: 'Incluye ver. Cargar lotes y enviar los avisos de pago a proveedores.' },
  'payments.admin': { label: 'Administrar pagos', description: 'Incluye todo lo anterior.' },
}

// Textos de un permiso; si no los hay, su código y el grupo por prefijo.
export function describePermission(code: string): { group: string; label: string; description: string } {
  const prefix = code.split('.')[0]
  return {
    group: GROUPS[prefix] ?? `Otros (${prefix})`,
    label: TEXTS[code]?.label ?? code,
    description: TEXTS[code]?.description ?? 'Sin descripción: permiso nuevo del catálogo de auth.',
  }
}

// Catálogo de auth con sus textos, agrupado y en orden estable.
export function withTexts(catalog: CatalogPermission[]): PermissionInfo[] {
  return catalog
    .map((p) => ({ ...p, ...describePermission(p.code) }))
    .sort((a, b) => a.group.localeCompare(b.group, 'es') || a.code.localeCompare(b.code))
}
