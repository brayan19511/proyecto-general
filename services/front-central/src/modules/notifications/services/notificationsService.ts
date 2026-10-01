import { apiDownload, apiRequest } from '../../../shared/api/apiClient'
import type {
  Attempt,
  Dispatch,
  DispatchStatus,
  MessageDetail,
  MessageStatus,
  MessageSummary,
  Page,
  Preview,
  SmtpAccount,
  SmtpAccountInput,
  SmtpTestResult,
  Template,
  TemplateInput,
} from '../types'

// Servicio notificaciones vía la central (/notificaciones). Valida empresa y
// permisos con auth; aquí solo se arma la solicitud.
const BASE = '/notificaciones'
export const PAGE_SIZE = 50

function query(params: Record<string, string | number | boolean | undefined>) {
  const q = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') q.set(key, String(value))
  const text = q.toString()
  return text ? `?${text}` : ''
}

// --- Envíos ---

export type DispatchFilters = {
  status?: DispatchStatus
  consumer?: string // origen, p. ej. "pagos-proveedores"
  requested_by_user_id?: string
  requester_email?: string // parte del correo del solicitante
}

export function listDispatches(filters: DispatchFilters, offset: number) {
  return apiRequest<Page<Dispatch>>(`${BASE}/dispatches${query({ ...filters, limit: PAGE_SIZE, offset })}`)
}

export function getDispatch(id: string) {
  return apiRequest<Dispatch>(`${BASE}/dispatches/${id}`)
}

export function listMessages(dispatchId: string, status: MessageStatus | undefined, offset: number) {
  return apiRequest<Page<MessageSummary>>(
    `${BASE}/dispatches/${dispatchId}/messages${query({ status, limit: PAGE_SIZE, offset })}`,
  )
}

// Reprocesa los failed y uncertain del envío.
export function retryDispatch(id: string, reason?: string) {
  return apiRequest<{ requeued: number }>(`${BASE}/dispatches/${id}/retry`, { method: 'POST', body: reason ? { reason } : {} })
}

// --- Mensajes ---

export function getMessage(id: string) {
  return apiRequest<MessageDetail>(`${BASE}/messages/${id}`)
}

export function retryMessage(id: string, reason?: string) {
  return apiRequest<MessageSummary>(`${BASE}/messages/${id}/retry`, { method: 'POST', body: reason ? { reason } : {} })
}

export function cancelMessage(id: string, reason?: string) {
  return apiRequest<MessageSummary>(`${BASE}/messages/${id}/cancel`, { method: 'POST', body: reason ? { reason } : {} })
}

export function listAttempts(id: string) {
  return apiRequest<Attempt[]>(`${BASE}/messages/${id}/attempts`)
}

export function downloadAttachment(messageId: string, attachmentId: string) {
  return apiDownload(`${BASE}/messages/${messageId}/attachments/${attachmentId}`)
}

// --- Cuentas SMTP (notifications.admin) ---

export function listSmtpAccounts(includeInactive: boolean) {
  return apiRequest<Page<SmtpAccount>>(`${BASE}/smtp-accounts${query({ include_inactive: includeInactive, limit: 200 })}`)
}

export function createSmtpAccount(input: SmtpAccountInput) {
  return apiRequest<SmtpAccount>(`${BASE}/smtp-accounts`, { method: 'POST', body: input })
}

export function updateSmtpAccount(id: string, changes: Partial<SmtpAccountInput>) {
  return apiRequest<SmtpAccount>(`${BASE}/smtp-accounts/${id}`, { method: 'PATCH', body: changes })
}

export function deleteSmtpAccount(id: string) {
  return apiRequest<void>(`${BASE}/smtp-accounts/${id}`, { method: 'DELETE' })
}

export function restoreSmtpAccount(id: string) {
  return apiRequest<SmtpAccount>(`${BASE}/smtp-accounts/${id}/restore`, { method: 'POST' })
}

// Conexión, TLS y autenticación; no envía correo.
export function testSmtpAccount(id: string) {
  return apiRequest<SmtpTestResult>(`${BASE}/smtp-accounts/${id}/test`, { method: 'POST' })
}

// --- Plantillas (notifications.admin) ---

export function listTemplates(includeInactive: boolean) {
  return apiRequest<Page<Template>>(`${BASE}/templates${query({ include_inactive: includeInactive, limit: 200 })}`)
}

export function createTemplate(input: TemplateInput) {
  return apiRequest<Template>(`${BASE}/templates`, { method: 'POST', body: input })
}

export function updateTemplate(id: string, changes: Partial<TemplateInput>) {
  return apiRequest<Template>(`${BASE}/templates/${id}`, { method: 'PATCH', body: changes })
}

export function deleteTemplate(id: string) {
  return apiRequest<void>(`${BASE}/templates/${id}`, { method: 'DELETE' })
}

export function restoreTemplate(id: string) {
  return apiRequest<Template>(`${BASE}/templates/${id}/restore`, { method: 'POST' })
}

export function previewTemplate(id: string, parameters: Record<string, unknown>) {
  return apiRequest<Preview>(`${BASE}/templates/${id}/preview`, { method: 'POST', body: { parameters } })
}
