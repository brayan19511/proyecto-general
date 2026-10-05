import { useState, type FormEvent } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { LASTMILLER_EDIT, LASTMILLER_IMPORT, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import { useChannel } from '../pages/ChannelLayout'
import * as lastmillerService from '../services/lastmillerService'
import type { Sku } from '../types'
import ImportModal from './ImportModal'
import SkuFormModal from './SkuFormModal'

type Pending = { kind: 'toggle' | 'promotion' | 'delete'; sku: Sku }

const EMPTY_FILTERS: lastmillerService.SkuFilters = { search: '', active: '', promotion: '' }

// SKU del canal. Cada consulta abre una conexión nueva a Ofisis (~1-2 s), así
// que la búsqueda se envía con el botón o Enter, no en cada tecla.
export default function SkusTab() {
  const channel = useChannel()
  const can = useCanAccess()
  const canEdit = can({ anyOf: LASTMILLER_EDIT })
  const canImport = can({ anyOf: LASTMILLER_IMPORT })
  const [draft, setDraft] = useState(EMPTY_FILTERS)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const skus = useApi(() => lastmillerService.listSkus(channel, filters, offset), [filters.search, filters.active, filters.promotion, offset])
  const [creating, setCreating] = useState(false)
  const [importing, setImporting] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)
  const [downloading, setDownloading] = useState(false)

  // Descarga lo filtrado (lo aplicado con Buscar, no lo que se está escribiendo).
  const download = async () => {
    setDownloading(true)
    try {
      await lastmillerService.exportSkus(channel, filters)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setDownloading(false)
    }
  }

  const apply =(next: lastmillerService.SkuFilters) => {
    setFilters(next)
    setOffset(0)
  }
  const search = (event: FormEvent) => {
    event.preventDefault()
    apply(draft)
  }

  const confirm = async () => {
    if (!pending) return
    const { kind, sku } = pending
    setBusy(true)
    try {
      if (kind === 'toggle') await lastmillerService.setSkuActive(channel, sku.sku, !sku.is_active)
      if (kind === 'promotion') await lastmillerService.setPromotion(channel, sku.sku, !sku.has_promotion)
      if (kind === 'delete') await lastmillerService.deleteSku(channel, sku.sku)
      toast.success(
        kind === 'toggle' ? `${sku.sku} quedó ${sku.is_active ? 'off' : 'on'}`
        : kind === 'promotion' ? `Promoción ${sku.has_promotion ? 'quitada de' : 'agregada a'} ${sku.sku}`
        : `${sku.sku} eliminado`,
      )
      skus.reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409: tiene promoción, bloqueado, cambió a la vez
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const columns: Column<Sku>[] = [
    { header: 'SKU', className: 'font-monospace text-nowrap', render: (s) => s.sku },
    { header: 'ID externo', className: 'font-monospace text-nowrap small text-body-secondary', render: (s) => s.external_id ?? '—' },
    {
      header: 'Estado',
      render: (s) => canEdit ? (
        <div className="form-check form-switch mb-0" title={s.is_active ? 'Desactivar' : 'Activar'}>
          <input type="checkbox" className="form-check-input" role="switch" checked={s.is_active}
            aria-label={`${s.is_active ? 'Desactivar' : 'Activar'} ${s.sku}`} onChange={() => setPending({ kind: 'toggle', sku: s })} />
          <span className={s.is_active ? 'text-success' : 'text-body-secondary'}>{s.is_active ? 'On' : 'Off'}</span>
        </div>
      ) : <StatusBadge tone={s.is_active ? 'success' : 'secondary'} label={s.is_active ? 'On' : 'Off'} />,
    },
    ...(channel.hasPromotions
      ? [{
          header: 'Promoción',
          render: (s: Sku) => canEdit ? (
            <button type="button" className={`btn btn-sm ${s.has_promotion ? 'btn-warning' : 'btn-outline-secondary'}`}
              onClick={() => setPending({ kind: 'promotion', sku: s })}
              title={s.has_promotion ? 'Quitar promoción' : 'Agregar promoción'}>
              <i className={`bi ${s.has_promotion ? 'bi-star-fill' : 'bi-star'}`} aria-hidden="true" />
              <span className="ms-1">{s.has_promotion ? 'Sí' : 'No'}</span>
            </button>
          ) : s.has_promotion ? <StatusBadge tone="warning" label="Con promoción" /> : <span className="text-body-secondary small">—</span>,
        }]
      : []),
    { header: 'Modificado', className: 'small text-nowrap text-body-secondary', render: (s) => (s.updated_at ? formatDateTime(s.updated_at) : '—') },
    ...(canEdit
      ? [{
          header: 'Acciones',
          className: 'text-end',
          render: (s: Sku) => (
            <button type="button" className="btn btn-sm btn-outline-danger" title="Eliminar" onClick={() => setPending({ kind: 'delete', sku: s })}>
              <i className="bi bi-trash" aria-hidden="true" />
              <span className="visually-hidden">Eliminar {s.sku}</span>
            </button>
          ),
        }]
      : []),
  ]

  const message = !pending ? ''
    : pending.kind === 'toggle'
      ? `${pending.sku.sku} pasará a ${pending.sku.is_active ? 'off: lastmiller dejará de ofrecerlo' : 'on: lastmiller lo ofrecerá'} en ${channel.name}.`
    : pending.kind === 'promotion'
      ? `${pending.sku.has_promotion ? 'Se quitará' : 'Se agregará'} la promoción de ${pending.sku.sku} en ${channel.name}.`
      : `${pending.sku.sku} se elimina de ${channel.name} (de la tabla que lee lastmiller). Queda registrado en el historial.`

  return (
    <>
      <form className="d-flex flex-wrap align-items-center gap-2 mb-3" onSubmit={search}>
        <input className="form-control form-control-sm" style={{ maxWidth: 260 }} placeholder="Buscar SKU…" aria-label="Buscar SKU"
          value={draft.search} onChange={(e) => setDraft({ ...draft, search: e.target.value })} />
        <select className="form-select form-select-sm w-auto" aria-label="Estado" value={draft.active}
          onChange={(e) => { const next = { ...draft, active: e.target.value as lastmillerService.SkuFilters['active'] }; setDraft(next); apply(next) }}>
          <option value="">Todos los estados</option>
          <option value="true">On</option>
          <option value="false">Off</option>
        </select>
        {channel.hasPromotions && (
          <select className="form-select form-select-sm w-auto" aria-label="Promoción" value={draft.promotion}
            onChange={(e) => { const next = { ...draft, promotion: e.target.value as lastmillerService.SkuFilters['promotion'] }; setDraft(next); apply(next) }}>
            <option value="">Con y sin promoción</option>
            <option value="true">Con promoción</option>
            <option value="false">Sin promoción</option>
          </select>
        )}
        <button type="submit" className="btn btn-sm btn-outline-primary">
          <i className="bi bi-search me-1" aria-hidden="true" />Buscar
        </button>
        <div className="ms-auto d-flex gap-2">
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={downloading} onClick={download}
            title="CSV con todos los SKU que cumplen los filtros aplicados">
            {downloading ? <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" /> : <i className="bi bi-download me-1" aria-hidden="true" />}
            Descargar CSV
          </button>
          {canImport && (
            <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setImporting(true)}>
              <i className="bi bi-file-earmark-arrow-up me-1" aria-hidden="true" />Carga masiva
            </button>
          )}
          {canEdit && (
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setCreating(true)}>
              <i className="bi bi-plus-lg me-1" aria-hidden="true" />Nuevo SKU
            </button>
          )}
        </div>
      </form>

      <AsyncState loading={skus.loading} error={skus.error} onRetry={skus.reload} hasData={skus.data !== undefined}>
        <DataTable columns={columns} rows={skus.data?.items ?? []} rowKey={(s) => s.sku}
          emptyMessage={filters.search || filters.active || filters.promotion ? 'Ningún SKU coincide.' : 'El canal no tiene SKU.'} />
        <Pager offset={offset} limit={lastmillerService.PAGE_SIZE} count={skus.data?.items.length ?? 0} total={skus.data?.total} onChange={setOffset} />
      </AsyncState>

      {creating && <SkuFormModal channel={channel} onClose={() => setCreating(false)} onSaved={skus.reload} />}
      {importing && <ImportModal channel={channel} onClose={() => setImporting(false)} onApplied={skus.reload} />}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'toggle' ? 'Cambiar estado' : pending?.kind === 'promotion' ? 'Cambiar promoción' : 'Eliminar SKU'}
        message={message}
        confirmLabel={pending?.kind === 'delete' ? 'Eliminar' : 'Confirmar'}
        danger={pending?.kind === 'delete'}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
