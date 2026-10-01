import { apiRequest } from '../../../shared/api/apiClient'
import type { GatewayHistoryEvent, GatewayService, IpBlock } from '../types'

// Administración de la central (solo platform admin). Los cambios aplican de
// inmediato en la réplica que responde y en las demás en ≤ GATEWAY_STATE_TTL_SECONDS.

export function listServices() {
  return apiRequest<GatewayService[]>('/gateway/admin/services')
}

// 409 si el servicio solo se cambia por configuración.
export function setServiceEnabled(service: string, isEnabled: boolean, reason: string | null) {
  return apiRequest<GatewayService>(`/gateway/admin/services/${encodeURIComponent(service)}`, {
    method: 'PATCH',
    body: { is_enabled: isEnabled, reason },
  })
}

export function listIpBlocks(includeInactive = false) {
  return apiRequest<IpBlock[]>(`/gateway/admin/ip-blocks?limit=500${includeInactive ? '&include_inactive=true' : ''}`)
}

// 422 IP/rango inválido o vencimiento pasado; 409 incluye tu IP o ya está bloqueado.
export function createIpBlock(network: string, reason: string | null, expiresAt: string | null) {
  return apiRequest<IpBlock>('/gateway/admin/ip-blocks', {
    method: 'POST',
    body: { network, reason, expires_at: expiresAt },
  })
}

export function deleteIpBlock(id: string) {
  return apiRequest<void>(`/gateway/admin/ip-blocks/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function listHistory(resourceType: 'service_state' | 'ip_block', limit = 20) {
  return apiRequest<GatewayHistoryEvent[]>(`/gateway/admin/history?resource_type=${resourceType}&limit=${limit}`)
}
