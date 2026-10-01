import type { BadgeTone } from '../../shared/components/StatusBadge'
import type { LogFilters, LogOutcome } from './types'

export const EMPTY_LOG_FILTERS: LogFilters = { outcome: '', userId: '', pathPrefix: '', traceId: '' }

export const OUTCOME: Record<LogOutcome, { label: string; tone: BadgeTone }> = {
  success: { label: 'Correcto', tone: 'success' },
  warning: { label: 'Advertencia', tone: 'warning' },
  error: { label: 'Error', tone: 'danger' },
}

export function formatDuration(ms: number | null) {
  if (ms === null) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`
}
