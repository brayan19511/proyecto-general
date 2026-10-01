import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { NOTIFICATIONS_VIEW, useHasCompanyScope } from '../../../shared/auth/access'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import DispatchDialog from '../components/DispatchDialog'
import { DISPATCH_STATUS } from '../labels'
import * as notificationsService from '../services/notificationsService'
import type { Dispatch, DispatchStatus } from '../types'

type DispatchesPageProps = {
  title: string
  description: string
  consumer: string // origen fijo: cada módulo ve solo los correos que envió
}

// Correos enviados por un módulo (p. ej. Tesorería › pagos-proveedores).
// Por defecto se ven los propios; "Todos los del módulo" solo aparece si el
// permiso vale en toda la empresa. Son filtros de presentación: lo que cada
// usuario puede ver lo decide notificaciones (empresa: todos; propio: los suyos).
export default function DispatchesPage({ title, description, consumer }: DispatchesPageProps) {
  const myId = useSessionStore((s) => s.me?.id)
  const [status, setStatus] = useState<DispatchStatus | ''>('')
  const canSeeAll = useHasCompanyScope(NOTIFICATIONS_VIEW)
  const [all, setAll] = useState(false)
  const mine = !(canSeeAll && all)
  const [email, setEmail] = useState('')
  const [offset, setOffset] = useState(0)
  const filters: notificationsService.DispatchFilters = {
    consumer,
    status: status || undefined,
    requested_by_user_id: mine ? myId : undefined,
    requester_email: mine ? undefined : email.trim() || undefined,
  }
  const dispatches = useApi(() => notificationsService.listDispatches(filters, offset), [filters, offset])
  const [open, setOpen] = useState<string | null>(null)

  const columns: Column<Dispatch>[] = [
    { header: 'Creado', className: 'text-nowrap', render: (d) => formatDateTime(d.created_at) },
    {
      header: 'Solicitado por',
      className: 'small',
      render: (d) => d.requested_by_email ?? <span className="text-body-secondary">Proceso automático</span>,
    },
    {
      header: 'Referencia',
      className: 'small font-monospace',
      render: (d) => d.consumer_reference ?? <span className="text-body-secondary">—</span>,
    },
    { header: 'Tipo', className: 'small', render: (d) => (d.kind === 'failure_notice' ? 'Aviso de fallo' : 'Normal') },
    {
      header: 'Progreso',
      className: 'text-nowrap',
      render: (d) => (
        <span className="small">
          {d.counts.sent}/{d.counts.total} enviados
          {d.counts.failed + d.counts.uncertain > 0 && <span className="text-danger"> · {d.counts.failed + d.counts.uncertain} con error</span>}
        </span>
      ),
    },
    { header: 'Estado', render: (d) => <StatusBadge {...DISPATCH_STATUS[d.status]} /> },
    {
      header: '',
      className: 'text-end',
      render: (d) => <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setOpen(d.id)}>Ver</button>,
    },
  ]

  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <select className="form-select form-select-sm w-auto" aria-label="Estado" value={status}
          onChange={(e) => { setStatus(e.target.value as DispatchStatus | ''); setOffset(0) }}>
          <option value="">Todos los estados</option>
          {(Object.keys(DISPATCH_STATUS) as DispatchStatus[]).map((s) => <option key={s} value={s}>{DISPATCH_STATUS[s].label}</option>)}
        </select>
        {canSeeAll && (
          <>
            <div className="btn-group btn-group-sm" role="group" aria-label="De quién">
              <button type="button" className={`btn btn-outline-primary ${!all ? 'active' : ''}`}
                onClick={() => { setAll(false); setOffset(0) }}>Mis correos</button>
              <button type="button" className={`btn btn-outline-primary ${all ? 'active' : ''}`}
                onClick={() => { setAll(true); setOffset(0) }}>Todos los del módulo</button>
            </div>
            {all && (
              <input className="form-control form-control-sm" style={{ maxWidth: 240 }} placeholder="Correo de quien lo pidió…"
                aria-label="Filtrar por usuario" value={email} onChange={(e) => { setEmail(e.target.value); setOffset(0) }} />
            )}
          </>
        )}
        <button type="button" className="btn btn-sm btn-outline-secondary ms-auto" onClick={dispatches.reload}>
          <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
          Actualizar
        </button>
      </div>

      <AsyncState loading={dispatches.loading} error={dispatches.error} onRetry={dispatches.reload} hasData={dispatches.data !== undefined}>
        <DataTable columns={columns} rows={dispatches.data?.items ?? []} rowKey={(d) => d.id} emptyMessage="No hay correos enviados." />
        <Pager offset={offset} limit={notificationsService.PAGE_SIZE} count={dispatches.data?.items.length ?? 0}
          total={dispatches.data?.total} onChange={setOffset} />
      </AsyncState>

      {open && <DispatchDialog dispatchId={open} onClose={() => setOpen(null)} onChanged={dispatches.reload} />}
    </>
  )
}
