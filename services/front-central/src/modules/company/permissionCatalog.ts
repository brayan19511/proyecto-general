// Copia del catálogo de permisos de auth (services/auth/app/core/permissions.py)
// con textos para la pantalla. Auth es la fuente de verdad: si se concede un
// permiso o alcance que no admite, responde 422. Al agregar un permiso en auth,
// agregarlo aquí (llega junto con la pantalla que lo usa).

export type PermissionScope = 'company' | 'area' | 'own'

export type PermissionInfo = {
  code: string
  group: string
  label: string
  description: string
  scopes: PermissionScope[] // los que admite auth para este permiso
}

export const SCOPE_LABEL: Record<PermissionScope, string> = {
  company: 'Toda la empresa',
  area: 'Solo su área',
  own: 'Solo lo propio',
}

export const SCOPE_HELP: Record<PermissionScope, string> = {
  company: 'Vale en toda la empresa activa.',
  area: 'Vale solo en el área del puesto que concede el rol.',
  own: 'Vale solo sobre recursos propios de la persona.',
}

export const PERMISSIONS: PermissionInfo[] = [
  { code: 'areas.manage', group: 'Organización', label: 'Gestionar áreas',
    description: 'Crear, renombrar, dar de baja y restaurar áreas.', scopes: ['company'] },
  { code: 'positions.manage', group: 'Organización', label: 'Gestionar puestos',
    description: 'Crear, editar y dar de baja puestos y asignarles roles.', scopes: ['company', 'area'] },
  { code: 'roles.manage', group: 'Organización', label: 'Gestionar roles',
    description: 'Crear roles y conceder o quitar sus permisos.', scopes: ['company'] },
  { code: 'memberships.manage', group: 'Organización', label: 'Gestionar miembros',
    description: 'Agregar, suspender y dar de baja miembros, y asignarles puestos.', scopes: ['company', 'area'] },
  { code: 'users.read', group: 'Organización', label: 'Ver miembros',
    description: 'Ver la lista de miembros y sus puestos.', scopes: ['company', 'area'] },
  { code: 'history.read', group: 'Organización', label: 'Ver historial',
    description: 'Ver quién cambió qué en la empresa.', scopes: ['company'] },
  { code: 'ledger.view', group: 'Libro mayor', label: 'Consultar libro mayor',
    description: 'Ver líneas, resumen, consultas en SAP, sincronización y reglas. Con "Solo su área", solo los centros de costo homologados a su área.',
    scopes: ['company', 'area'] },
  { code: 'ledger.update', group: 'Libro mayor', label: 'Editar reglas y categorías',
    description: 'Incluye consultar. Crear y editar reglas y categorías, y reclasificar.', scopes: ['company'] },
  { code: 'ledger.admin', group: 'Libro mayor', label: 'Administrar libro mayor',
    description: 'Incluye lo anterior. Cuentas, sincronización manual y homologación de centros de costo.', scopes: ['company'] },
]

export function permissionInfo(code: string): PermissionInfo | undefined {
  return PERMISSIONS.find((p) => p.code === code)
}
