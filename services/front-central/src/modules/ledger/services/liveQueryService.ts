import { apiRequest } from '../../../shared/api/apiClient'
import type { LiveQueryRequest, LiveQueryResult } from '../types'

// Consulta SAP en la misma solicitud (puede tardar; libro-mayor corta a los
// LIVE_QUERY_TIMEOUT_SECONDS). No es idempotente en costo: no se reintenta.
export function runLiveQuery(body: LiveQueryRequest) {
  return apiRequest<LiveQueryResult>('/libro-mayor/live-queries', { method: 'POST', body })
}
