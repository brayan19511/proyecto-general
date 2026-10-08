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

// Correos: uno por línea, o separados por coma o punto y coma (un correo nunca
// lleva esos caracteres); quita vacíos.
export function splitLines(text: string): string[] {
  return text.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean)
}

// Nombres comerciales: SOLO uno por línea. Un nombre puede llevar comas
// ("Hebei Huishi Technology Co., Ltd"); partirlo por la coma guardaría "Ltd"
// como un nombre más, que luego choca con otros proveedores.
export function splitByLine(text: string): string[] {
  return text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
}
