import { apiDownload, apiRequest } from '../../../shared/api/apiClient'
import { saveBlob } from '../../../shared/utils/download'
import type { ItemStatus, Job, JobEvent, JobItem, JobItemDetail, JobKind, JobListItem, JobStatus, Page, Preview, SapDatabase } from '../types'

const BASE = '/sap-operaciones'
export const PAGE_SIZE = 50
export const MAX_FILE_BYTES = 20 * 1024 * 1024

// --- Vista previa: crea el trabajo en borrador (no ejecuta nada en SAP).

export function previewDocumentAction(input: { company_db: string; entity: string; action: string; documents: string }) {
  return apiRequest<Preview>(`${BASE}/jobs/document-actions/preview`, { method: 'POST', body: input })
}

export function previewReconciliation(companyDb: string, reconDate: string, file: File) {
  const form = new FormData()
  form.append('company_db', companyDb)
  form.append('recon_date', reconDate)
  form.append('file', file, file.name)
  return apiRequest<Preview>(`${BASE}/jobs/reconciliations/preview`, { method: 'POST', body: form })
}

// --- Ciclo de vida

// Prueba el inicio de sesión en SAP y deja el trabajo en cola (lo ejecuta el worker).
export function enqueue(jobId: string, sapUser: string, sapPassword: string) {
  return apiRequest<Job>(`${BASE}/jobs/${jobId}/enqueue`, { method: 'POST', body: { sap_user: sapUser, sap_password: sapPassword } })
}

// Sin credenciales usa las guardadas; con ambas, las reemplaza.
export function resume(jobId: string, sapUser?: string, sapPassword?: string) {
  const body = sapUser && sapPassword ? { sap_user: sapUser, sap_password: sapPassword } : {}
  return apiRequest<Job>(`${BASE}/jobs/${jobId}/resume`, { method: 'POST', body })
}

export function cancel(jobId: string) {
  return apiRequest<Job>(`${BASE}/jobs/${jobId}/cancel`, { method: 'POST' })
}

// Solo administrador de plataforma; queda en el historial. Nunca guardar ni registrar en consola.
export function revealCredentials(jobId: string) {
  return apiRequest<{ sap_user: string | null; sap_password: string }>(`${BASE}/jobs/${jobId}/credentials`)
}

// --- Consultas

export function listJobs(filters: { status: JobStatus | ''; kind: JobKind | '' }, offset: number) {
  const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
  if (filters.status) q.set('status', filters.status)
  if (filters.kind) q.set('kind', filters.kind)
  return apiRequest<Page<JobListItem>>(`${BASE}/jobs?${q}`)
}

export function getJob(jobId: string) {
  return apiRequest<Job>(`${BASE}/jobs/${jobId}`)
}

export function listItems(jobId: string, filters: { status: ItemStatus | ''; reference: string }, offset: number) {
  const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
  if (filters.status) q.set('status', filters.status)
  if (filters.reference.trim()) q.set('reference', filters.reference.trim())
  return apiRequest<Page<JobItem>>(`${BASE}/jobs/${jobId}/items?${q}`)
}

export function listEvents(jobId: string) {
  return apiRequest<JobEvent[]>(`${BASE}/jobs/${jobId}/events`)
}

// --- Bases SAP sugeridas

export function listDatabases() {
  return apiRequest<SapDatabase[]>(`${BASE}/databases`)
}

export function createDatabase(companyDb: string, label: string) {
  return apiRequest<SapDatabase>(`${BASE}/databases`, { method: 'POST', body: { company_db: companyDb, label: label || null } })
}

export function deleteDatabase(id: string) {
  return apiRequest<void>(`${BASE}/databases/${id}`, { method: 'DELETE' })
}

// --- Configuración SAP de la empresa (URL del Service Layer)

export type SapSettings = { service_layer_url: string | null; source: 'company' | 'default'; verify_tls: boolean; updated_at: string | null }

export function getSettings() {
  return apiRequest<SapSettings>(`${BASE}/settings`)
}

// Solo platform admin. null = volver a la URL del despliegue.
export function updateSettings(serviceLayerUrl: string | null) {
  return apiRequest<SapSettings>(`${BASE}/settings`, { method: 'PATCH', body: { service_layer_url: serviceLayerUrl } })
}

// --- Detalle y descargas

export function getItem(jobId: string, seq: number) {
  return apiRequest<JobItemDetail>(`${BASE}/jobs/${jobId}/items/${seq}`)
}

// CSV con todos los ítems del trabajo (estado y respuesta de SAP).
export async function exportItems(jobId: string) {
  const { blob, filename } = await apiDownload(`${BASE}/jobs/${jobId}/items/export`)
  saveBlob(blob, filename ?? `sap-trabajo-${jobId.slice(0, 8)}.csv`)
}
