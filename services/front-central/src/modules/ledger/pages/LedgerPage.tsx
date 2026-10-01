import { useState } from 'react'
import EmptyState from '../../../shared/components/EmptyState'
import PageHeader from '../../../shared/components/PageHeader'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { saveBlob } from '../../../shared/utils/download'
import { toIsoDate } from '../../../shared/utils/format'
import LedgerFiltersBar from '../components/LedgerFiltersBar'
import LedgerResults from '../components/LedgerResults'
import * as ledgerService from '../services/ledgerService'
import type { LedgerFilters } from '../types'

// Valores iniciales del formulario: del 1 de enero hasta hoy, todas las cuentas.
function defaultFilters(): LedgerFilters {
  const today = new Date()
  return {
    dateFrom: toIsoDate(new Date(today.getFullYear(), 0, 1)),
    dateTo: toIsoDate(today),
    accounts: '',
    costCenterCode: '',
  }
}

// Libro mayor (ledger.view o superior; con alcance de área, libro-mayor solo
// devuelve las líneas de tus áreas). No consulta hasta pulsar "Consultar".
export default function LedgerPage() {
  const [applied, setApplied] = useState<LedgerFilters | null>(null)
  const [runs, setRuns] = useState(0) // cada "Consultar" vuelve a consultar, aunque los filtros no cambien
  const [exporting, setExporting] = useState(false)
  const accounts = useApi(ledgerService.listAccounts)

  const downloadAll = async () => {
    if (!applied) return
    setExporting(true)
    try {
      const { blob, filename } = await ledgerService.downloadLinesCsv(applied)
      saveBlob(blob, filename ?? 'libro_mayor.csv')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setExporting(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Libro mayor"
        description="Gastos por categoría, subcategoría, proveedor y mes. Haz clic en un importe para ver sus líneas."
        actions={
          <button
            type="button"
            className="btn btn-outline-secondary"
            onClick={downloadAll}
            disabled={exporting || !applied}
            title={applied ? undefined : 'Primero realiza una consulta'}
          >
            {exporting ? <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" /> : <i className="bi bi-filetype-csv me-1" aria-hidden="true" />}
            CSV completo
          </button>
        }
      />

      <LedgerFiltersBar initial={applied ?? defaultFilters()} accounts={accounts.data ?? []}
        onApply={(f) => {
          setApplied(f)
          setRuns((n) => n + 1)
        }}
      />

      {applied ? (
        // key: cada consulta empieza de cero (árbol plegado, sin detalle abierto).
        <LedgerResults key={runs} filters={applied} />
      ) : (
        <EmptyState
          icon="search"
          title="Elige los filtros y pulsa Consultar"
          description="Acota el rango, las cuentas o el centro de costo para obtener el resultado más rápido."
        />
      )}
    </>
  )
}
