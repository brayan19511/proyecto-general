import { apiRequest } from '../../../shared/api/apiClient'
import type { AdminUser, LogEntry, LogFilters, LogFull } from '../types'

// Cada servicio expone solo sus propios logs (regla de observabilidad). Todas
// las rutas exigen platform admin y pasan por la central.
export const LOG_SERVICES = [
  { key: 'gateway', label: 'Central', base: '/gateway/admin/logs', loginPath: '/auth/login' },
  { key: 'auth', label: 'Auth', base: '/auth/admin/logs', loginPath: '/auth/login' },
  { key: 'libro-mayor', label: 'Libro mayor', base: '/libro-mayor/admin/logs', loginPath: null },
] as const

export type LogServiceKey = (typeof LOG_SERVICES)[number]['key']

export const LOGS_PAGE_SIZE = 50

export function findLogService(key: string | undefined) {
  return LOG_SERVICES.find((s) => s.key === key)
}

function baseOf(service: LogServiceKey) {
  return LOG_SERVICES.find((s) => s.key === service)!.base
}

// Más recientes primero.
export function listLogs(service: LogServiceKey, filters: LogFilters, offset: number, limit = LOGS_PAGE_SIZE) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (filters.outcome) params.set('outcome', filters.outcome)
  if (filters.userId) params.set('user_id', filters.userId)
  if (filters.pathPrefix.trim()) params.set('path_prefix', filters.pathPrefix.trim())
  if (filters.traceId.trim()) params.set('trace_id', filters.traceId.trim())
  return apiRequest<LogEntry[]>(`${baseOf(service)}?${params}`)
}

export function getLog(service: LogServiceKey, logId: string) {
  return apiRequest<LogFull>(`${baseOf(service)}/${encodeURIComponent(logId)}`)
}

// Traza completa: la misma solicitud vista en cada servicio. Un servicio caído
// o deshabilitado no impide ver los demás.
export async function getTrace(traceId: string) {
  const filters: LogFilters = { outcome: '', userId: '', pathPrefix: '', traceId }
  const results = await Promise.allSettled(LOG_SERVICES.map((s) => listLogs(s.key, filters, 0, 100)))
  const entries = results.flatMap((r, i) =>
    r.status === 'fulfilled' ? r.value.map((log) => ({ service: LOG_SERVICES[i].key, log })) : [],
  )
  const failed = results.flatMap((r, i) => (r.status === 'rejected' ? [LOG_SERVICES[i].label] : []))
  entries.sort((a, b) => a.log.started_at.localeCompare(b.log.started_at))
  return { entries, failed }
}

// Para mostrar correos en lugar de ids. 500 es el máximo por página de auth.
export function listUsers() {
  return apiRequest<AdminUser[]>('/auth/admin/users?limit=500')
}
