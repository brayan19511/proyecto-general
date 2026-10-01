import { apiRequest } from '../../shared/api/apiClient'

// API keys propias en la empresa activa (services/auth, /auth/api-keys).
// Solo con sesión iniciada: una API key no puede crear ni revocar keys.

export type ApiKey = {
  id: string
  name: string
  description: string | null
  prefix: string // parte visible para reconocerla
  scopes: string[] // permisos que puede usar (nunca más que los del dueño)
  company_id: string
  expires_at: string | null // null: sin vencimiento
  revoked_at: string | null
  last_used_at: string | null
  created_at: string
}

// La respuesta de crear trae el secreto UNA sola vez.
export type ApiKeyCreated = ApiKey & { key: string }

export type ApiKeyInput = {
  name: string
  description?: string
  scopes: string[]
  expires_in_days?: number // sin esto, la key no vence
}

// Máximo de keys vigentes por usuario (API_KEYS_MAX de auth, 5 por defecto).
export const API_KEYS_MAX = 5

// Servicios que hoy aceptan X-API-Key. Una key con permisos de otro servicio
// no sirve allí (notificaciones y pagos-proveedores solo aceptan sesión).
export const API_KEY_SERVICES = 'libro-mayor'

export function keyStatus(k: ApiKey, now: number): 'revoked' | 'expired' | 'active' {
  if (k.revoked_at) return 'revoked'
  if (k.expires_at && new Date(k.expires_at).getTime() <= now) return 'expired'
  return 'active'
}

export function listMyApiKeys() {
  return apiRequest<ApiKey[]>('/auth/api-keys')
}

export function createApiKey(input: ApiKeyInput) {
  return apiRequest<ApiKeyCreated>('/auth/api-keys', { method: 'POST', body: input })
}

// Irreversible: la key deja de funcionar de inmediato.
export function revokeApiKey(id: string) {
  return apiRequest<void>(`/auth/api-keys/${encodeURIComponent(id)}`, { method: 'DELETE' })
}
