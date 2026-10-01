import { useSessionStore } from './sessionStore'
import type { PermissionGrant } from '../../modules/auth/types'

// Reglas de visibilidad de módulos y rutas. Es experiencia de usuario, no
// seguridad: el backend valida cada solicitud aunque el front muestre algo.
//
// - 'authenticated': cualquier usuario con sesión.
// - 'platformAdmin': solo platform admin.
// - { anyOf: [...] }: al menos uno de esos permisos en la empresa activa
//   (con cualquier alcance: empresa, área o propio).
//
// El platform admin pasa todas las reglas sin necesitar permisos (acuerdo).
export type AccessRule = 'authenticated' | 'platformAdmin' | { anyOf: string[] }

// Cada nivel de libro mayor incluye al anterior (lo aplica libro-mayor).
export const LEDGER_VIEW = ['ledger.view', 'ledger.update', 'ledger.admin']
export const LEDGER_UPDATE = ['ledger.update', 'ledger.admin'] // reglas, categorías, reclasificar
export const LEDGER_ADMIN = ['ledger.admin'] // cuentas, sincronización manual, homologación

export function canAccess(
  rule: AccessRule,
  isPlatformAdmin: boolean,
  permissions: PermissionGrant[],
): boolean {
  if (isPlatformAdmin) return true
  if (rule === 'authenticated') return true
  if (rule === 'platformAdmin') return false
  return permissions.some((p) => rule.anyOf.includes(p.code))
}

// Hook para componentes: devuelve una función que evalúa reglas con la sesión actual.
export function useCanAccess() {
  const isPlatformAdmin = useSessionStore((s) => s.me?.is_platform_admin ?? false)
  const permissions = useSessionStore((s) => s.permissions)
  return (rule: AccessRule) => canAccess(rule, isPlatformAdmin, permissions)
}
