import { apiDownload, apiRequest } from '../../../shared/api/apiClient'
import { saveBlob } from '../../../shared/utils/download'
import type { Attachment, DocumentSearch, DocumentSearchPage, DocumentType, Download, DownloadListItem, DownloadMode, FileSelection } from '../documentTypes'
import type { Page } from '../types'

// Documentos SAP y descargas de anexos (permiso sap_documents.view).
const BASE = '/sap-operaciones/documents'
export const SEARCH_PAGE_SIZE = 50
export const DOWNLOADS_PAGE_SIZE = 50
export const MAX_DOWNLOAD_FILES = 50

export function listTypes() {
  return apiRequest<DocumentType[]>(`${BASE}/types`)
}

// Solo se envían los filtros con valor (el backend exige un criterio exacto o socio + fechas).
export function search(filters: DocumentSearch, offset: number) {
  const q = new URLSearchParams({ limit: String(SEARCH_PAGE_SIZE), offset: String(offset) })
  for (const [key, value] of Object.entries(filters)) {
    if (value && String(value).trim()) q.set(key, String(value).trim())
  }
  return apiRequest<DocumentSearchPage>(`${BASE}/search?${q}`)
}

export function listAttachments(companyDb: string, typeCode: string, docEntry: number) {
  const q = new URLSearchParams({ company_db: companyDb })
  return apiRequest<Attachment[]>(`${BASE}/${encodeURIComponent(typeCode)}/${docEntry}/attachments?${q}`)
}

// --- Descargas: primero se registran (quién y qué), después se bajan.

export function createDownload(companyDb: string, mode: DownloadMode, files: FileSelection[]) {
  return apiRequest<Download>(`${BASE}/downloads`, { method: 'POST', body: { company_db: companyDb, mode, files } })
}

export async function saveFile(downloadId: string, seq: number, fallbackName: string) {
  const { blob, filename } = await apiDownload(`${BASE}/downloads/${downloadId}/files/${seq}`)
  saveBlob(blob, filename ?? fallbackName)
}

export async function saveZip(downloadId: string) {
  const { blob, filename } = await apiDownload(`${BASE}/downloads/${downloadId}/zip`)
  saveBlob(blob, filename ?? `anexos-${downloadId.slice(0, 8)}.zip`)
}

export function listDownloads(offset: number) {
  const q = new URLSearchParams({ limit: String(DOWNLOADS_PAGE_SIZE), offset: String(offset) })
  return apiRequest<Page<DownloadListItem>>(`${BASE}/downloads?${q}`)
}

export function getDownload(downloadId: string) {
  return apiRequest<Download>(`${BASE}/downloads/${downloadId}`)
}
