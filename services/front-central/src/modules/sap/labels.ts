import type { BadgeTone } from '../../shared/components/StatusBadge'
import type { ItemStatus, JobKind, JobStatus } from './types'

export const KIND_LABEL: Record<JobKind, string> = {
  document_action: 'Acción sobre documentos',
  reconciliation: 'Conciliación interna',
}

export const JOB_STATUS: Record<JobStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Borrador', tone: 'secondary' },
  queued: { label: 'En cola', tone: 'info' },
  running: { label: 'En proceso', tone: 'warning' },
  completed: { label: 'Completado', tone: 'success' },
  completed_with_errors: { label: 'Con errores', tone: 'danger' },
  failed: { label: 'Detenido', tone: 'danger' },
  cancelled: { label: 'Cancelado', tone: 'secondary' },
}

export const ITEM_STATUS: Record<ItemStatus, { label: string; tone: BadgeTone }> = {
  pending: { label: 'Pendiente', tone: 'secondary' },
  running: { label: 'En curso', tone: 'warning' },
  succeeded: { label: 'Correcto', tone: 'success' },
  failed: { label: 'Error de SAP', tone: 'danger' },
  uncertain: { label: 'Incierto', tone: 'warning' },
  cancelled: { label: 'Cancelado', tone: 'secondary' },
}

export const EVENT_LABEL: Record<string, string> = {
  'job.created': 'Vista previa creada',
  'job.queued': 'Enviado a ejecutar',
  'job.cancel_requested': 'Cancelación pedida',
  'job.cancelled': 'Cancelado',
  'job.resumed': 'Reanudado',
  'job.stopped': 'Detenido',
  'job.recovered': 'Retomado tras caída del worker',
  'job.finished': 'Terminado',
  'job.credentials_viewed': 'Credenciales vistas por el administrador',
}

// Acciones habituales del Service Layer como sugerencia (son libres: decisión 2026-10-04).
export const SUGGESTED_ENTITIES = ['Invoices', 'CreditNotes', 'Orders', 'PurchaseOrders', 'PurchaseInvoices', 'DeliveryNotes', 'Quotations', 'JournalEntries']
export const SUGGESTED_ACTIONS = ['Cancel', 'Close', 'Reopen']

export function isOpen(status: JobStatus) {
  return status === 'queued' || status === 'running'
}
