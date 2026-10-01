import { apiDownload, apiRequest } from '../../../shared/api/apiClient'
import type { Account, LedgerDetailFilters, LedgerFilters, LedgerLinesPage, SummaryRow } from '../types'

// Parámetros de la URL comunes a lines, lines.csv y summary.
function toParams(f: LedgerDetailFilters): URLSearchParams {
  const params = new URLSearchParams({ date_from: f.dateFrom, date_to: f.dateTo })
  if (f.accounts.trim()) params.set('accounts', f.accounts.replace(/\s+/g, ''))
  if (f.costCenterCode.trim()) params.set('cost_center_code', f.costCenterCode.trim())
  if (f.codigo) params.set('codigo', f.codigo)
  if (f.subcodigo) params.set('subcodigo', f.subcodigo)
  if (f.noSubcodigo) params.set('no_subcodigo', 'true')
  if (f.unclassified !== undefined) params.set('unclassified', String(f.unclassified))
  if (f.supplier) params.set('supplier', f.supplier)
  if (f.noSupplier) params.set('no_supplier', 'true')
  return params
}

// Agrupado también por proveedor: tercer nivel del árbol.
export function getSummary(filters: LedgerFilters) {
  const params = toParams(filters)
  params.set('by_supplier', 'true')
  return apiRequest<SummaryRow[]>(`/libro-mayor/ledger/summary?${params}`)
}

// Cuentas registradas de la empresa, para el selector de filtros.
export function listAccounts() {
  return apiRequest<Account[]>('/libro-mayor/accounts?limit=500')
}

export function listLines(filters: LedgerDetailFilters, offset: number, limit: number) {
  const params = toParams(filters)
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  return apiRequest<LedgerLinesPage>(`/libro-mayor/ledger/lines?${params}`)
}

// Todas las líneas del filtro con todas las columnas, generado por libro-mayor
// (streaming, sin límite). ";" para Excel en español.
export function downloadLinesCsv(filters: LedgerFilters) {
  const params = toParams(filters)
  params.set('sep', ';')
  return apiDownload(`/libro-mayor/ledger/lines.csv?${params}`)
}

// Tope de líneas que el navegador junta para la descarga con columnas elegidas.
// Por encima conviene el CSV completo de libro-mayor.
export const DETAIL_EXPORT_MAX = 50_000
const EXPORT_PAGE = 5000 // máximo que admite /ledger/lines

export async function fetchAllLines(filters: LedgerDetailFilters) {
  const lines = []
  let offset: number | null = 0
  while (offset !== null && lines.length < DETAIL_EXPORT_MAX) {
    const page: LedgerLinesPage = await listLines(filters, offset, EXPORT_PAGE)
    lines.push(...page.lines)
    offset = page.next_offset
  }
  return lines
}
