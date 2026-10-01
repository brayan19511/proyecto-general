import type { BadgeTone } from '../../shared/components/StatusBadge'
import type { BatchStatus, GroupStatus } from './types'

export const BATCH_STATUS: Record<BatchStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Borrador', tone: 'secondary' },
  sending: { label: 'Enviando', tone: 'info' },
  sent: { label: 'Enviado', tone: 'success' },
}

export const GROUP_STATUS: Record<GroupStatus, { label: string; tone: BadgeTone }> = {
  READY: { label: 'Listo', tone: 'success' },
  MISSING_PROVIDER: { label: 'Sin proveedor', tone: 'danger' },
  MISSING_PAYMENT_EMAIL: { label: 'Sin correo', tone: 'warning' },
}

// Una línea por valor (nombres comerciales, correos); quita vacíos.
export function splitLines(text: string): string[] {
  return text.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean)
}
