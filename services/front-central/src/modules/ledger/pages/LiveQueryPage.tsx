import { useEffect, useState } from 'react'
import EmptyState from '../../../shared/components/EmptyState'
import PageHeader from '../../../shared/components/PageHeader'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { saveBlob, toCsv } from '../../../shared/utils/download'
import LineDetailDialog from '../components/LineDetailDialog'
import LiveQueryForm from '../components/LiveQueryForm'
import SummaryView from '../components/SummaryView'
import { lineMatches, selectionRange, selectionTitle, type TreeSelection } from '../detailSelection'
import { LINE_COLUMNS } from '../lineColumns'
import * as ledgerService from '../services/ledgerService'
import * as liveQueryService from '../services/liveQueryService'
import { linesToRows } from '../summaryTree'
import type { LedgerLine, LiveQueryRequest, LiveQueryResult } from '../types'

const numberFormat = new Intl.NumberFormat('es-PE')

// Consulta directa a SAP (ledger.view). Útil para ver lo más reciente o cuentas
// no sincronizadas. El resultado vive solo en esta página: no se guarda.
export default function LiveQueryPage() {
  const accounts = useApi(ledgerService.listAccounts)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<LiveQueryResult | null>(null)
  const [selection, setSelection] = useState<TreeSelection | null>(null)

  // Segundos de espera visibles mientras SAP responde.
  useEffect(() => {
    if (!running) return
    const started = Date.now()
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [running])

  const run = async (request: LiveQueryRequest) => {
    setRunning(true)
    setElapsed(0)
    setError(null)
    setResult(null)
    setSelection(null)
    try {
      setResult(await liveQueryService.runLiveQuery(request))
    } catch (err) {
      setError(errorMessage(err)) // 422 demasiadas líneas o rango, 409 sin SAP, 502 SAP falló, 504 tiempo
    } finally {
      setRunning(false)
    }
  }

  const lines = result?.lines ?? null
  // Con líneas se arma el árbol con proveedor; con "solo resumen", hasta subcategoría.
  const rows = lines ? linesToRows(lines) : result?.summary ?? []
  const range = result ? { dateFrom: result.date_from, dateTo: result.date_to } : null

  // Detalle desde memoria, con la misma forma paginada que libro-mayor.
  const detailLines = (): LedgerLine[] => {
    if (!lines || !selection || !range) return []
    const r = selectionRange(range, selection.month)
    return lines.filter((l) => lineMatches(l, selection.node?.filters ?? {}, r))
  }

  const downloadAll = () => {
    if (!lines || !result) return
    const blob = toCsv(lines, LINE_COLUMNS.map((c) => ({ header: c.label, value: (l: LedgerLine) => l[c.key] })))
    saveBlob(blob, `consulta_sap_${result.date_from}_${result.date_to}.csv`)
  }

  return (
    <>
      <PageHeader
        title="Consulta en SAP"
        description="Consulta SAP en este momento y clasifica con las reglas actuales. El resultado no se guarda."
        actions={
          lines && (
            <button type="button" className="btn btn-outline-secondary" onClick={downloadAll}>
              <i className="bi bi-filetype-csv me-1" aria-hidden="true" />
              CSV completo
            </button>
          )
        }
      />

      <LiveQueryForm accounts={accounts.data ?? []} busy={running} onRun={run} />

      {running && (
        <div className="alert alert-info d-flex align-items-center gap-2" role="status">
          <span className="spinner-border spinner-border-sm" aria-hidden="true" />
          Consultando SAP… {elapsed} s. Puede tardar hasta un par de minutos; no cierres esta página.
        </div>
      )}
      {error && <div className="alert alert-danger" role="alert">{error}</div>}

      {result && (
        <>
          <p className="small text-body-secondary">
            {numberFormat.format(result.lines_total)} líneas · {result.chunks} tramos · {(result.elapsed_ms / 1000).toFixed(1)} s
            {!lines && ' · Solo resumen: sin proveedor ni detalle.'}
          </p>
          <SummaryView rows={rows} onSelect={lines ? setSelection : undefined} />
        </>
      )}

      {!running && !result && !error && (
        <EmptyState
          icon="lightning-charge"
          title="Elige cuentas y rango, y consulta"
          description="Para reportes del día a día usa Libro mayor (datos ya sincronizados): es mucho más rápido."
        />
      )}

      {selection && range && (
        <LineDetailDialog
          title={selectionTitle(selection)}
          range={selectionRange(range, selection.month)}
          loadPage={async (offset, limit) => {
            const all = detailLines()
            const page = all.slice(offset, offset + limit)
            const next = offset + page.length
            return { total: all.length, limit, offset, next_offset: next < all.length ? next : null, lines: page }
          }}
          loadAll={async () => detailLines()}
          onClose={() => setSelection(null)}
        />
      )}
    </>
  )
}
