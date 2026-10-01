import { apiDownload, apiRequest } from '../../../shared/api/apiClient'
import type { Batch, BatchStatus, BatchSummary, DeliveryStatus, Page, PaymentSettings, Provider, ProviderInput } from '../types'

// Servicio pagos-proveedores vía la central (/pagos-proveedores).
const BASE = '/pagos-proveedores'
export const PAGE_SIZE = 50

// Límites de pagos-proveedores (batch_service.py) y del borde (100 MB por solicitud).
export const MAX_FILES = 100
export const MAX_FILE_BYTES = 25 * 1024 * 1024
export const MAX_REQUEST_BYTES = 100 * 1024 * 1024

// --- Proveedores ---

export function listProviders(search: string, includeInactive: boolean, offset: number) {
  const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
  if (search) q.set('search', search)
  if (includeInactive) q.set('include_inactive', 'true')
  return apiRequest<Page<Provider>>(`${BASE}/providers?${q}`)
}

export function getProvider(id: string) {
  return apiRequest<Provider>(`${BASE}/providers/${id}`)
}

export function createProvider(input: ProviderInput) {
  return apiRequest<Provider>(`${BASE}/providers`, { method: 'POST', body: input })
}

export function updateProvider(id: string, changes: Partial<ProviderInput>) {
  return apiRequest<Provider>(`${BASE}/providers/${id}`, { method: 'PATCH', body: changes })
}

export function deleteProvider(id: string) {
  return apiRequest<void>(`${BASE}/providers/${id}`, { method: 'DELETE' })
}

export function restoreProvider(id: string) {
  return apiRequest<Provider>(`${BASE}/providers/${id}/restore`, { method: 'POST' })
}

// --- Lotes ---

export function listBatches(status: BatchStatus | undefined, offset: number) {
  const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
  if (status) q.set('status', status)
  return apiRequest<Page<BatchSummary>>(`${BASE}/batches?${q}`)
}

// Sube las constancias y las lee en la misma solicitud (puede tardar: OCR).
export function createBatch(files: File[], reference: string) {
  const form = new FormData()
  for (const file of files) form.append('files', file, file.name)
  if (reference) form.append('reference', reference)
  return apiRequest<Batch>(`${BASE}/batches`, { method: 'POST', body: form })
}

// En borrador los grupos se recalculan con el maestro actual en cada consulta.
export function getBatch(id: string) {
  return apiRequest<Batch>(`${BASE}/batches/${id}`)
}

export function downloadFile(batchId: string, fileId: string) {
  return apiDownload(`${BASE}/batches/${batchId}/files/${fileId}`)
}

export function downloadZip(batchId: string) {
  return apiDownload(`${BASE}/batches/${batchId}/zip`)
}

export function removeFile(batchId: string, fileId: string) {
  return apiRequest<void>(`${BASE}/batches/${batchId}/files/${fileId}`, { method: 'DELETE' })
}

export function discardBatch(batchId: string, reason?: string) {
  return apiRequest<void>(`${BASE}/batches/${batchId}`, { method: 'DELETE', body: reason ? { reason } : undefined })
}

// template_code: solo payments.admin (si no, 403); vacío = la configurada en el servicio.
export function sendBatch(batchId: string, options: { template_code?: string; subject?: string; message?: string }) {
  return apiRequest<Batch>(`${BASE}/batches/${batchId}/send`, { method: 'POST', body: options })
}

// --- Configuración de la empresa ---

export function getSettings() {
  return apiRequest<PaymentSettings>(`${BASE}/settings`)
}

// Solo payments.admin. null = volver a la plantilla del servicio.
export function updateSettings(defaultTemplateCode: string | null) {
  return apiRequest<PaymentSettings>(`${BASE}/settings`, { method: 'PATCH', body: { default_template_code: defaultTemplateCode } })
}

export function getDeliveryStatus(batchId: string) {
  return apiRequest<DeliveryStatus>(`${BASE}/batches/${batchId}/delivery-status`)
}
