import StatusBadge, { type BadgeTone } from '../../../shared/components/StatusBadge'
import { OUTCOME } from '../logLabels'
import type { LogOutcome } from '../types'

export function OutcomeBadge({ outcome }: { outcome: LogOutcome | null }) {
  if (!outcome) return <StatusBadge tone="secondary" label="Sin cerrar" />
  return <StatusBadge {...OUTCOME[outcome]} />
}

// 2xx verde, 4xx ámbar, 5xx rojo.
export function HttpStatus({ code }: { code: number | null }) {
  if (code === null) return <span className="text-body-secondary">—</span>
  const tone: BadgeTone = code >= 500 ? 'danger' : code >= 400 ? 'warning' : 'success'
  return <StatusBadge tone={tone} label={String(code)} />
}
