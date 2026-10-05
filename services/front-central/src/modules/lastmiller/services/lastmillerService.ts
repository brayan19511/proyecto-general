import { apiDownload, apiRequest } from '../../../shared/api/apiClient'
import { saveBlob } from '../../../shared/utils/download'
import type { Channel } from '../channels'
import type { ImportDetail, ImportKind, ImportSummary, Page, Sku, SkuEvent } from '../types'

export const PAGE_SIZE = 50
export const MAX_FILE_BYTES = 10 * 1024 * 1024

function base(channel: Channel) {
  return `/canales-venta/lastmiller/${channel.country}/${channel.provider}`
}

function skuPath(channel: Channel, sku: string) {
  return `${base(channel)}/skus/${encodeURIComponent(sku)}`
}

export type SkuFilters = { search: string; active: '' | 'true' | 'false'; promotion: '' | 'true' | 'false' }

export function listSkus(channel: Channel, filters: SkuFilters, offset: number) {
  const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
  if (filters.search.trim()) q.set('search', filters.search.trim())
  if (filters.active) q.set('active', filters.active)
  if (filters.promotion && channel.hasPromotions) q.set('promotion', filters.promotion)
  return apiRequest<Page<Sku>>(`${base(channel)}/skus?${q}`)
}

// El id externo no se envía: canales-venta usa el mismo sku.
export function createSku(channel: Channel, sku: string, isActive: boolean) {
  return apiRequest<Sku>(`${base(channel)}/skus`, { method: 'POST', body: { sku, is_active: isActive } })
}

export function setSkuActive(channel: Channel, sku: string, isActive: boolean) {
  return apiRequest<Sku>(skuPath(channel, sku), { method: 'PATCH', body: { is_active: isActive } })
}

export function deleteSku(channel: Channel, sku: string) {
  return apiRequest<void>(skuPath(channel, sku), { method: 'DELETE' })
}

export function setPromotion(channel: Channel, sku: string, enabled: boolean) {
  return apiRequest<Sku>(`${skuPath(channel, sku)}/promotion`, { method: enabled ? 'POST' : 'DELETE' })
}

// Lee el archivo y devuelve qué cambiaría. No modifica nada hasta applyImport.
export function previewImport(channel: Channel, kind: ImportKind, createMissing: boolean, file: File) {
  const form = new FormData()
  form.append('kind', kind)
  form.append('create_missing', String(createMissing))
  form.append('file', file, file.name)
  return apiRequest<ImportDetail>(`${base(channel)}/imports/preview`, { method: 'POST', body: form })
}

export function applyImport(channel: Channel, importId: string) {
  return apiRequest<ImportDetail>(`${base(channel)}/imports/${importId}/apply`, { method: 'POST' })
}

// Descarta una vista previa sin aplicarla (no toca Ofisis).
export function cancelImport(channel: Channel, importId: string) {
  return apiRequest<ImportDetail>(`${base(channel)}/imports/${importId}/cancel`, { method: 'POST' })
}

export function listImports(channel: Channel, offset: number) {
  return apiRequest<Page<ImportSummary>>(`${base(channel)}/imports?limit=${PAGE_SIZE}&offset=${offset}`)
}

export function getImport(channel: Channel, importId: string) {
  return apiRequest<ImportDetail>(`${base(channel)}/imports/${importId}`)
}

export function listHistory(channel: Channel, filters: { sku: string; importId: string }, offset: number) {
  const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
  if (filters.sku.trim()) q.set('sku', filters.sku.trim())
  if (filters.importId) q.set('import_id', filters.importId)
  return apiRequest<Page<SkuEvent>>(`${base(channel)}/history?${q}`)
}

// Consolidado en CSV de los SKU con los filtros aplicados (todas las páginas).
export async function exportSkus(channel: Channel, filters: SkuFilters) {
  const q = new URLSearchParams()
  if (filters.search.trim()) q.set('search', filters.search.trim())
  if (filters.active) q.set('active', filters.active)
  if (filters.promotion && channel.hasPromotions) q.set('promotion', filters.promotion)
  const { blob, filename } = await apiDownload(`${base(channel)}/skus/export?${q}`)
  saveBlob(blob, filename ?? `skus-${channel.country}-${channel.provider}.csv`)
}
