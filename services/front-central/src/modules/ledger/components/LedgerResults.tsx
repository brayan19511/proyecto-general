import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import { useApi } from '../../../shared/hooks/useApi'
import { selectionRange, selectionTitle, type TreeSelection } from '../detailSelection'
import * as ledgerService from '../services/ledgerService'
import type { LedgerDetailFilters, LedgerFilters } from '../types'
import LineDetailDialog from './LineDetailDialog'
import SummaryView from './SummaryView'

// Resultado de una consulta del Libro mayor (líneas ya sincronizadas).
// Se monta recién al pulsar "Consultar".
export default function LedgerResults({ filters }: { filters: LedgerFilters }) {
  const summary = useApi(() => ledgerService.getSummary(filters), [JSON.stringify(filters)])
  const [selection, setSelection] = useState<TreeSelection | null>(null)

  // Filtros del detalle: los de la consulta + los del nodo y el mes elegidos.
  const detail: LedgerDetailFilters | null = selection && {
    ...filters,
    ...selection.node?.filters,
    ...selectionRange(filters, selection.month),
  }

  return (
    <>
      <AsyncState loading={summary.loading} error={summary.error} onRetry={summary.reload} hasData={summary.data !== undefined}>
        <SummaryView rows={summary.data ?? []} onSelect={setSelection} />
      </AsyncState>

      {selection && detail && (
        <LineDetailDialog
          title={selectionTitle(selection)}
          range={detail}
          loadPage={(offset, limit) => ledgerService.listLines(detail, offset, limit)}
          loadAll={() => ledgerService.fetchAllLines(detail)}
          exportLimit={ledgerService.DETAIL_EXPORT_MAX}
          onClose={() => setSelection(null)}
        />
      )}
    </>
  )
}
