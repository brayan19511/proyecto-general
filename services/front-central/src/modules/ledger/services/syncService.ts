import { apiRequest } from '../../../shared/api/apiClient'
import type { SyncRun, SyncRunFilters, SyncStatus } from '../types'

export const SYNC_RUNS_PAGE_SIZE = 20

export function getSyncStatus() {
  return apiRequest<SyncStatus[]>('/libro-mayor/sync-status')
}

// Registra una sincronización manual (202, queda "pendiente"); la procesa el
// worker. Sin reintentos: libro-mayor rechaza con 409 una segunda abierta.
export function createSyncRun(accountId: string, dateFrom: string, dateTo: string) {
  return apiRequest<SyncRun>('/libro-mayor/sync-runs', {
    method: 'POST',
    body: { account_id: accountId, date_from: dateFrom, date_to: dateTo },
  })
}

// Más recientes primero. Filtros opcionales por estado y cuenta.
export function listSyncRuns({ status, accountId, offset }: SyncRunFilters) {
  const params = new URLSearchParams({ limit: String(SYNC_RUNS_PAGE_SIZE), offset: String(offset) })
  if (status) params.set('status', status)
  if (accountId) params.set('account_id', accountId)
  return apiRequest<SyncRun[]>(`/libro-mayor/sync-runs?${params}`)
}
