import { apiRequest } from '../../../shared/api/apiClient'
import type { AdminUser, AdminUserDetail } from '../types'

// Usuarios de toda la plataforma (auth, solo platform admin).
const id = encodeURIComponent
export const USERS_PAGE_SIZE = 50

// email: coincidencia parcial; vacío = todos.
export function searchUsers(email: string, offset: number) {
  const params = new URLSearchParams({ limit: String(USERS_PAGE_SIZE), offset: String(offset) })
  if (email.trim()) params.set('email', email.trim())
  return apiRequest<AdminUser[]>(`/auth/admin/users?${params}`)
}

export function getUser(userId: string) {
  return apiRequest<AdminUserDetail>(`/auth/admin/users/${id(userId)}`)
}

// Asigna una contraseña nueva y cierra sus sesiones.
export function resetPassword(userId: string, newPassword: string) {
  return apiRequest<{ revoked: number }>(`/auth/admin/users/${id(userId)}/password`, {
    method: 'POST',
    body: { new_password: newPassword },
  })
}

export function revokeSessions(userId: string) {
  return apiRequest<{ revoked: number }>(`/auth/admin/users/${id(userId)}/revoke-sessions`, { method: 'POST' })
}

// Correo por id, para mostrar quién hizo un cambio (hasta 500 usuarios).
export async function emailsById() {
  const users = await apiRequest<AdminUser[]>('/auth/admin/users?limit=500')
  return new Map(users.map((u) => [u.id, u.email]))
}
