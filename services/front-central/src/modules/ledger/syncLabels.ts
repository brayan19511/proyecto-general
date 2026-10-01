import type { BadgeTone } from '../../shared/components/StatusBadge'
import type { SyncRun, SyncRunStatus } from './types'

// Textos y colores de los valores que devuelve libro-mayor.

export const RUN_STATUS: Record<SyncRunStatus, { label: string; tone: BadgeTone }> = {
  pending: { label: 'Pendiente', tone: 'secondary' },
  running: { label: 'En curso', tone: 'info' },
  succeeded: { label: 'Correcta', tone: 'success' },
  failed: { label: 'Fallida', tone: 'danger' },
}

export const RUN_KIND: Record<SyncRun['kind'], string> = {
  sync: 'Manual',
  initial: 'Carga inicial',
  delta: 'Programada',
}
