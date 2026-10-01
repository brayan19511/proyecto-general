import { apiRequest } from '../../../shared/api/apiClient'
import type { Profile } from '../../auth/types'
import type { Country, MyProfile, MySession, ProfileUpdate } from '../types'

export function getMyProfile() {
  return apiRequest<MyProfile>('/auth/me/profile')
}

export function updateMyProfile(data: ProfileUpdate) {
  return apiRequest<Profile>('/auth/me/profile', { method: 'PATCH', body: data })
}

export function listCountries() {
  return apiRequest<Country[]>('/auth/catalog/countries')
}

// Devuelve cuántas sesiones se cerraron (todas menos la actual).
export function changeMyPassword(currentPassword: string, newPassword: string) {
  return apiRequest<{ revoked: number }>('/auth/me/password', {
    method: 'PATCH',
    body: { current_password: currentPassword, new_password: newPassword },
  })
}

export function listMySessions() {
  return apiRequest<MySession[]>('/auth/me/sessions')
}

export function revokeMySession(sessionId: string) {
  return apiRequest<void>(`/auth/me/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

export function revokeMyOtherSessions() {
  return apiRequest<{ revoked: number }>('/auth/me/sessions/revoke-others', { method: 'POST' })
}
