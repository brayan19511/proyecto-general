import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { PAYMENTS_ADMIN, PAYMENTS_SEND, useCanAccess } from '../../../shared/auth/access'
import { useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import NewBatchModal from '../components/NewBatchModal'
import SettingsModal from '../components/SettingsModal'
import { BATCH_STATUS } from '../labels'
import * as paymentsService from '../services/paymentsService'
import type { BatchStatus, BatchSummary } from '../types'

// Tesorería › Pagos a proveedores: cada carga de constancias, de borrador a enviado.
export default function BatchesPage() {
  const can = useCanAccess()
  const navigate = useNavigate()
  const [status, setStatus] = useState<BatchStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const batches = useApi(() => paymentsService.listBatches(status || undefined, offset), [status, offset])
  const [creating, setCreating] = useState(false)
  const isAdmin = can({ anyOf: PAYMENTS_ADMIN })
  const settings = useApi(() => (isAdmin ? paymentsService.getSettings() : Promise.resolve(null)), [isAdmin])
  const [configuring, setConfiguring] = useState(false)

  const columns: Column<BatchSummary>[] = [
    { header: 'Creado', className: 'text-nowrap', render: (b) => formatDateTime(b.created_at) },
    { header: 'Referencia', render: (b) => b.reference ?? <span className="text-body-secondary">—</span> },
    { header: 'Constancias', className: 'text-end', render: (b) => b.file_count },
    { header: 'Estado', render: (b) => <StatusBadge {...BATCH_STATUS[b.status]} /> },
    { header: 'Enviado', className: 'text-nowrap small', render: (b) => (b.sent_at ? formatDateTime(b.sent_at) : '—') },
    {
      header: '',
      className: 'text-end',
      render: (b) => <Link to={`/tesoreria/pagos/${b.id}`} className="btn btn-sm btn-outline-secondary">Abrir</Link>,
    },
  ]

  return (
    <>
      <PageHeader
        title="Lotes de pago"
        description="Sube las constancias, revisa a qué proveedor corresponde cada una y envía los avisos por correo."
        actions={
          <>
            {isAdmin && settings.data && (
              <button type="button" className="btn btn-outline-secondary me-2" onClick={() => setConfiguring(true)}
                title={`Plantilla de los avisos: ${settings.data.effective_template_code}`}>
                <i className="bi bi-gear me-1" aria-hidden="true" />
                Plantilla por defecto
              </button>
            )}
            {can({ anyOf: PAYMENTS_SEND }) && (
              <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
                <i className="bi bi-upload me-1" aria-hidden="true" />
                Nuevo lote
              </button>
            )}
          </>
        }
      />
      <div className="d-flex align-items-center gap-2 mb-3">
        <select className="form-select form-select-sm w-auto" aria-label="Estado" value={status}
          onChange={(e) => { setStatus(e.target.value as BatchStatus | ''); setOffset(0) }}>
          <option value="">Todos los estados</option>
          {(Object.keys(BATCH_STATUS) as BatchStatus[]).map((s) => <option key={s} value={s}>{BATCH_STATUS[s].label}</option>)}
        </select>
      </div>
      <AsyncState loading={batches.loading} error={batches.error} onRetry={batches.reload} hasData={batches.data !== undefined}>
        <DataTable columns={columns} rows={batches.data?.items ?? []} rowKey={(b) => b.id} emptyMessage="Aún no hay lotes." />
        <Pager offset={offset} limit={paymentsService.PAGE_SIZE} count={batches.data?.items.length ?? 0}
          total={batches.data?.total} onChange={setOffset} />
      </AsyncState>

      {configuring && settings.data && (
        <SettingsModal current={settings.data} onClose={() => setConfiguring(false)} onSaved={settings.reload} />
      )}
      {creating && (
        <NewBatchModal
          onClose={() => setCreating(false)}
          onCreated={(b) => {
            toast.success(`Lote creado: ${b.counts.parsed} de ${b.counts.files} constancias leídas`)
            navigate(`/tesoreria/pagos/${b.id}`)
          }}
        />
      )}
    </>
  )
}
