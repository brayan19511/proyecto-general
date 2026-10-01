import { apiRequest } from '../../../shared/api/apiClient'
import type { HistoryEvent } from '../types'

export const HISTORY_PAGE_SIZE = 50

export type HistoryFilters = {
  action: string // prefijo, p. ej. "membership."
  actorId: string
  resourceId: string
}

// Historial de la empresa activa (history.read). Solo eventos de esta empresa:
// los globales (usuarios, sesiones) no tienen empresa y no aparecen.
export function listHistory(filters: HistoryFilters, offset: number) {
  const params = new URLSearchParams({ limit: String(HISTORY_PAGE_SIZE), offset: String(offset) })
  if (filters.action) params.set('action', filters.action)
  if (filters.actorId) params.set('actor_id', filters.actorId)
  if (filters.resourceId.trim()) params.set('resource_id', filters.resourceId.trim())
  return apiRequest<HistoryEvent[]>(`/auth/history?${params}`)
}
