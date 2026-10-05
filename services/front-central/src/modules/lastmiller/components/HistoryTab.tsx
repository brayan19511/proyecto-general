import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import Pager from '../../../shared/components/Pager'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import { ACTION_LABEL } from '../labels'
import { useChannel } from '../pages/ChannelLayout'
import * as lastmillerService from '../services/lastmillerService'
import type { SkuEvent } from '../types'

// Historial de cambios de los SKU hechos desde la plataforma (individuales y
// por cargas). Cambios hechos en Ofisis por otros sistemas no aparecen aquí.
export default function HistoryTab() {
  const channel = useChannel()
  const [params, setParams] = useSearchParams()
  const importId = params.get('carga') ?? ''
  const [draft, setDraft] = useState('')
  const [sku, setSku] = useState('')
  const [offset, setOffset] = useState(0)
  const events = useApi(() => lastmillerService.listHistory(channel, { sku, importId }, offset), [sku, importId, offset])

  const search = (event: FormEvent) => {
    event.preventDefault()
    setSku(draft.trim())
    setOffset(0)
  }
  const filterImport = (id: string | null) => {
    setParams(id ? { carga: id } : {})
    setOffset(0)
  }

  const columns: Column<SkuEvent>[] = [
    { header: 'Fecha', className: 'small text-nowrap', render: (e) => formatDateTime(e.created_at) },
    {
      header: 'SKU',
      className: 'font-monospace text-nowrap',
      render: (e) => (
        <button type="button" className="btn btn-link btn-sm p-0 font-monospace" title="Ver solo este SKU"
          onClick={() => { setDraft(e.sku); setSku(e.sku); setOffset(0) }}>{e.sku}</button>
      ),
    },
    { header: 'Cambio', render: (e) => ACTION_LABEL[e.action] ?? e.action },
    {
      header: 'Origen',
      className: 'small',
      render: (e) => e.import_id
        ? <button type="button" className="btn btn-link btn-sm p-0" onClick={() => filterImport(e.import_id)}>Carga masiva</button>
        : 'Individual',
    },
    // canales-venta guarda el id del usuario de auth (sin nombre ni email).
    { header: 'Usuario', className: 'small font-monospace text-body-secondary', render: (e) => <span title={e.user_id}>{e.user_id.slice(0, 8)}</span> },
  ]

  return (
    <>
      <form className="d-flex flex-wrap align-items-center gap-2 mb-3" onSubmit={search}>
        <input className="form-control form-control-sm" style={{ maxWidth: 260 }} placeholder="SKU exacto…" aria-label="Filtrar por SKU"
          value={draft} onChange={(e) => setDraft(e.target.value)} />
        <button type="submit" className="btn btn-sm btn-outline-primary">Filtrar</button>
        {sku && <button type="button" className="btn btn-sm btn-link" onClick={() => { setDraft(''); setSku(''); setOffset(0) }}>Quitar SKU</button>}
        {importId && (
          <span className="badge bg-info-subtle text-info-emphasis fw-normal d-inline-flex align-items-center gap-1">
            Solo una carga masiva
            <button type="button" className="btn btn-link p-0 lh-1" aria-label="Quitar filtro de carga" onClick={() => filterImport(null)}>
              <i className="bi bi-x-lg" aria-hidden="true" />
            </button>
          </span>
        )}
      </form>
      <AsyncState loading={events.loading} error={events.error} onRetry={events.reload} hasData={events.data !== undefined}>
        <DataTable columns={columns} rows={events.data?.items ?? []} rowKey={(e) => e.id} emptyMessage="Sin cambios registrados." />
        <Pager offset={offset} limit={lastmillerService.PAGE_SIZE} count={events.data?.items.length ?? 0} total={events.data?.total} onChange={setOffset} />
      </AsyncState>
    </>
  )
}
