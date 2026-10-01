import { apiRequest } from '../../../shared/api/apiClient'
import type { TokenResponse } from '../../../shared/auth/tokens'
import type { AdminCompany, CompanyPermissions, Me } from '../types'

export function login(email: string, password: string) {
  return apiRequest<TokenResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: false,
  })
}

// Responde 204 siempre; cierra la sesión en el servidor.
export function logout(refreshToken: string) {
  return apiRequest<void>('/auth/logout', {
    method: 'POST',
    body: { refresh_token: refreshToken },
    auth: false,
  })
}

export function getMe() {
  return apiRequest<Me>('/auth/me')
}

// La empresa va explícita: se consulta antes de activarla en el selector.
export function getMyPermissions(companyId: string) {
  return apiRequest<CompanyPermissions>('/auth/me/permissions', { companyId })
}

// Solo platform admin. 500 es el máximo que admite auth por página.
export function listAllCompanies() {
  return apiRequest<AdminCompany[]>('/auth/admin/companies?limit=500')
}
