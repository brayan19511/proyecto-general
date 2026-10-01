import { apiRequest } from '../../../shared/api/apiClient'
import type { Member } from '../types'

// Miembros de la empresa activa. Leer: users.read; cambiar: memberships.manage
// (fase 1: el front solo lo muestra al platform admin). Auth valida todo:
// alcance de área, no dejar la empresa sin administradores, etc.

export const MEMBERS_PAGE_SIZE = 100

export function listMembers(offset: number) {
  return apiRequest<Member[]>(`/auth/members?limit=${MEMBERS_PAGE_SIZE}&offset=${offset}`)
}

// Agrega a un usuario YA registrado, por su email exacto (no crea cuentas).
export function addMember(email: string) {
  return apiRequest<Member>('/auth/members', { method: 'POST', body: { email } })
}

// false = suspender (pierde el acceso, conserva sus puestos); true = reactivar.
export function setMemberActive(membershipId: string, isActive: boolean) {
  return apiRequest<Member>(`/auth/members/${encodeURIComponent(membershipId)}`, {
    method: 'PATCH',
    body: { is_active: isActive },
  })
}

// Baja: deja la empresa y se retiran todos sus puestos (cada uno con historial).
export function removeMember(membershipId: string) {
  return apiRequest<void>(`/auth/members/${encodeURIComponent(membershipId)}`, { method: 'DELETE' })
}

export function assignPosition(membershipId: string, positionId: string) {
  return apiRequest<Member>(`/auth/members/${encodeURIComponent(membershipId)}/positions`, {
    method: 'POST',
    body: { position_id: positionId },
  })
}

export function unassignPosition(membershipId: string, positionId: string) {
  return apiRequest<void>(
    `/auth/members/${encodeURIComponent(membershipId)}/positions/${encodeURIComponent(positionId)}`,
    { method: 'DELETE' },
  )
}

// Registro de cuenta (ruta pública de auth: correo + contraseña). No da acceso
// a ninguna empresa: después se agrega con addMember. Auth limita los registros
// por IP (REGISTER_IP_LIMIT por hora).
export function registerUser(email: string, password: string) {
  return apiRequest<{ id: string; email: string }>('/auth/users', {
    method: 'POST',
    body: { email, password },
    auth: false,
  })
}
