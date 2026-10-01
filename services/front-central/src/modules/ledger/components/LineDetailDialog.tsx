import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import CheckboxDropdown from '../../../shared/components/CheckboxDropdown'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import Dialog from '../../../shared/components/Dialog'
import Pager from '../../../shared/components/Pager'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { saveBlob, toCsv } from '../../../shared/utils/download'
import { formatDate } from '../../../shared/utils/format'
import type { DateRange } from '../detailSelection'
import { DEFAULT_COLUMN_KEYS, LINE_COLUMNS, showValue } from '../lineColumns'
import type { LedgerLine, LedgerLinesPage } from '../types'

const PAGE_SIZE = 200
const COLUMNS_KEY = 'ledger.detail.columns' // preferencia del navegador (comodidad)

function readColumns(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(COLUMNS_KEY) ?? 'null')
    const valid = Array.isArray(saved) ? saved.filter((k) => LINE_COLUMNS.some((c) => c.key === k)) : []
    return valid.length > 0 ? valid : DEFAULT_COLUMN_KEYS
  } catch {
    return DEFAULT_COLUMN_KEYS
  }
}

type LineDetailDialogProps = {
  title: string
  range: DateRange
  // De dónde salen las líneas: libro-mayor (paginado) o memoria (consulta en vivo).
  loadPage: (offset: number, limit: number) => Promise<LedgerLinesPage>
  loadAll: () => Promise<LedgerLine[]>
  exportLimit?: number // si loadAll corta, cuántas líneas trae como máximo
  onClose: () => void
}

// Detalle de una celda del árbol: líneas paginadas, columnas elegibles y
// descarga CSV de las columnas visibles. Se monta al abrirse.
export default function LineDetailDialog({ title, range, loadPage, loadAll, exportLimit, onClose }: LineDetailDialogProps) {
  const [offset, setOffset] = useState(0)
  const [columnKeys, setColumnKeys] = useState(readColumns)
  const [exporting, setExporting] = useState(false)

  const query = useApi(() => loadPage(offset, PAGE_SIZE), [offset])
  const total = query.data?.total ?? 0

  const visible = LINE_COLUMNS.filter((c) => columnKeys.includes(c.key))
  const tableColumns: Column<LedgerLine>[] = visible.map((c) => ({
    header: c.label,
    className: c.amount ? 'text-end text-nowrap' : c.date ? 'text-nowrap' : undefined,
    render: (line) => showValue(c, line),
  }))

  const changeColumns = (selected: string[]) => {
    const keys = selected.length > 0 ? selected : DEFAULT_COLUMN_KEYS.slice(0, 1) // al menos una
    setColumnKeys(keys)
    try {
      localStorage.setItem(COLUMNS_KEY, JSON.stringify(keys))
    } catch {
      // sin almacenamiento la elección dura hasta cerrar la página
    }
  }

  // Descarga con las columnas visibles (valores crudos: importes con punto y signo).
  const downloadVisible = async () => {
    setExporting(true)
    try {
      const lines = await loadAll()
      const blob = toCsv(lines, visible.map((c) => ({ header: c.label, value: (l: LedgerLine) => l[c.key] })))
      saveBlob(blob, `detalle_${range.dateFrom}_${range.dateTo}.csv`)
      if (exportLimit !== undefined && total > exportLimit) {
        toast.warning(`Se descargaron las primeras ${exportLimit} líneas. Para todas, usa el CSV completo.`)
      }
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setExporting(false)
    }
  }

  return (
    <Dialog open wide onClose={onClose} busy={exporting} labelledBy="detail-title">
      <div className="card-header bg-transparent d-flex flex-wrap align-items-center gap-2">
        <div className="me-auto">
          <h2 id="detail-title" className="h5 mb-0">{title}</h2>
          <div className="small text-body-secondary">
            {formatDate(range.dateFrom)} – {formatDate(range.dateTo)}
            {query.data && ` · ${new Intl.NumberFormat('es-PE').format(total)} líneas`}
          </div>
        </div>
        <CheckboxDropdown
          label="Columnas"
          icon="layout-three-columns"
          options={LINE_COLUMNS.map((c) => ({ key: c.key, label: c.label }))}
          selected={columnKeys}
          onChange={changeColumns}
        />
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={downloadVisible} disabled={exporting || total === 0}>
          {exporting ? <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" /> : <i className="bi bi-download me-1" aria-hidden="true" />}
          Descargar
        </button>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} disabled={exporting} />
      </div>

      <div className="card-body">
        <AsyncState loading={query.loading} error={query.error} onRetry={query.reload} hasData={query.data !== undefined}>
          <DataTable
            columns={tableColumns}
            rows={query.data?.lines ?? []}
            rowKey={(l) => `${l.sap_transaction_id}-${l.sap_line}`}
            emptyMessage="No hay líneas para esta selección."
          />
          <Pager offset={offset} limit={PAGE_SIZE} count={query.data?.lines.length ?? 0} total={total} onChange={setOffset} />
        </AsyncState>
      </div>
    </Dialog>
  )
}
