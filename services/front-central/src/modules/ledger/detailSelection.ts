import { toIsoDate } from '../../shared/utils/format'
import { NO_CATEGORY, NO_SUBCATEGORY, NO_SUPPLIER, type Month, type TreeNode } from './summaryTree'
import type { LedgerLine, NodeFilters } from './types'

// Qué celda del árbol se eligió: un nodo (null = todas las categorías, fila de
// total) y opcionalmente un mes (null = todo el rango consultado).
export type TreeSelection = { node: TreeNode | null; month: Month | null }

export type DateRange = { dateFrom: string; dateTo: string }

// Rango de la celda: el mes recortado al rango consultado, o el rango entero.
export function selectionRange(base: DateRange, month: Month | null): DateRange {
  if (!month) return base
  const first = toIsoDate(new Date(month.year, month.month - 1, 1))
  const last = toIsoDate(new Date(month.year, month.month, 0))
  return {
    dateFrom: first > base.dateFrom ? first : base.dateFrom,
    dateTo: last < base.dateTo ? last : base.dateTo,
  }
}

// Ruta del nodo, p. ej. "GASTOS ADM › Luz › LUZ DEL SUR S.A.A.".
export function selectionTitle({ node }: TreeSelection): string {
  const f = node?.filters
  if (!f) return 'Todas las categorías'
  return [
    f.unclassified ? NO_CATEGORY : f.codigo,
    f.subcodigo ?? (f.noSubcodigo ? NO_SUBCATEGORY : undefined),
    f.supplier ?? (f.noSupplier ? NO_SUPPLIER : undefined),
  ].filter(Boolean).join(' › ')
}

const blank = (text: string | null) => !text || !text.trim()

// Mismo criterio que libro-mayor, para filtrar en el navegador las líneas de una
// consulta en vivo (ver ledger_query_service._conditions).
export function lineMatches(line: LedgerLine, f: NodeFilters, range: DateRange): boolean {
  if (line.posting_date < range.dateFrom || line.posting_date > range.dateTo) return false
  if (f.unclassified && line.rule_id !== null) return false
  if (f.codigo && line.codigo !== f.codigo) return false
  if (f.subcodigo && line.subcodigo !== f.subcodigo) return false
  if (f.noSubcodigo && (line.codigo === null || line.subcodigo !== null)) return false
  if (f.supplier && line.supplier !== f.supplier) return false
  if (f.noSupplier && !blank(line.supplier)) return false
  return true
}
