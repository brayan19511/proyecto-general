import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import Dialog from '../../../shared/components/Dialog'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { NOTIFICATIONS_RETRY, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import { DISPATCH_STATUS, MESSAGE_STATUS } from '../labels'
import * as notificationsService from '../services/notificationsService'
import type { MessageStatus, MessageSummary } from '../types'
import MessageDialog from './MessageDialog'

// Un envío: progreso por estado y sus mensajes. Reprocesar todo lo fallido.
export default function DispatchDialog({ dispatchId, onClose, onChanged }: { dispatchId: string; onClose: () => void; onChanged: () => void }) {
  const can = useCanAccess()
  const [status, setStatus] = useState<MessageStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const dispatch = useApi(() => notificationsService.getDispatch(dispatchId), [dispatchId])
  const messages = useApi(() => notificationsService.listMessages(dispatchId, status || undefined, offset), [dispatchId, status, offset])
  const [openMessage, setOpenMessage] = useState<string | null>(null)
  const [confirmRetry, setConfirmRetry] = useState(false)
  const [busy, setBusy] = useState(false)
  const d = dispatch.data
  const failed = d ? d.counts.failed + d.counts.uncertain : 0

  const reload = () => {
    dispatch.reload()
    messages.reload()
    onChanged()
  }

  const retryAll = async () => {
    setBusy(true)
    try {
      const { requeued } = await notificationsService.retryDispatch(dispatchId)
      toast.success(requeued === 0 ? 'No había mensajes para reprocesar' : `${requeued} mensajes en cola de nuevo`)
      reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setConfirmRetry(false)
    }
  }

  const columns: Column<MessageSummary>[] = [
    { header: '#', className: 'text-body-secondary', render: (m) => m.sequence },
    { header: 'Para', render: (m) => <span className="text-break">{m.to.join(', ') || '—'}</span> },
    { header: 'Asunto', render: (m) => m.subject },
    { header: 'Estado', render: (m) => <StatusBadge {...MESSAGE_STATUS[m.status]} /> },
    { header: 'Enviado', className: 'text-nowrap small', render: (m) => (m.sent_at ? formatDateTime(m.sent_at) : '—') },
    {
      header: '',
      className: 'text-end',
      render: (m) => (
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setOpenMessage(m.id)}>Ver</button>
      ),
    },
  ]

  return (
    <Dialog open wide onClose={onClose} labelledBy="dispatch-title">
      <div className="card-header bg-transparent d-flex align-items-center gap-2">
        <h2 id="dispatch-title" className="h5 mb-0 me-auto">
          Envío {d?.consumer_reference ?? dispatchId.slice(0, 8)}
        </h2>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} />
      </div>
      <div className="card-body">
        <AsyncState loading={dispatch.loading} error={dispatch.error} onRetry={dispatch.reload} hasData={d !== undefined}>
          {d && (
            <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
              <StatusBadge {...DISPATCH_STATUS[d.status]} />
              <span className="small text-body-secondary">
                {d.consumer ?? 'Sin origen'} · {formatDateTime(d.created_at)} · {d.counts.sent} de {d.counts.total} enviados
              </span>
              {(Object.keys(MESSAGE_STATUS) as MessageStatus[])
                .filter((s) => d.counts[s] > 0)
                .map((s) => (
                  <span key={s} className="badge text-bg-light border fw-normal">{MESSAGE_STATUS[s].label}: {d.counts[s]}</span>
                ))}
              <button type="button" className="btn btn-sm btn-outline-secondary ms-auto" onClick={reload} title="Actualizar">
                <i className="bi bi-arrow-clockwise" aria-hidden="true" />
                <span className="visually-hidden">Actualizar</span>
              </button>
              {can({ anyOf: NOTIFICATIONS_RETRY }) && failed > 0 && (
                <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setConfirmRetry(true)}>
                  <i className="bi bi-arrow-repeat me-1" aria-hidden="true" />
                  Reprocesar fallidos ({failed})
                </button>
              )}
            </div>
          )}
        </AsyncState>

        <div className="d-flex align-items-center gap-2 mb-2">
          <label htmlFor="msg-status" className="small text-body-secondary">Estado</label>
          <select id="msg-status" className="form-select form-select-sm w-auto" value={status}
            onChange={(e) => { setStatus(e.target.value as MessageStatus | ''); setOffset(0) }}>
            <option value="">Todos</option>
            {(Object.keys(MESSAGE_STATUS) as MessageStatus[]).map((s) => <option key={s} value={s}>{MESSAGE_STATUS[s].label}</option>)}
          </select>
        </div>
        <AsyncState loading={messages.loading} error={messages.error} onRetry={messages.reload} hasData={messages.data !== undefined}>
          <DataTable columns={columns} rows={messages.data?.items ?? []} rowKey={(m) => m.id} emptyMessage="No hay mensajes con ese estado." />
          <Pager offset={offset} limit={notificationsService.PAGE_SIZE} count={messages.data?.items.length ?? 0}
            total={messages.data?.total} onChange={setOffset} />
        </AsyncState>
      </div>

      {openMessage && <MessageDialog messageId={openMessage} onClose={() => setOpenMessage(null)} onChanged={reload} />}
      <ConfirmDialog
        open={confirmRetry}
        title="Reprocesar fallidos"
        message={`Vuelven a la cola ${failed} mensajes fallidos o inciertos. Los inciertos quizá ya llegaron: podrían recibirse dos veces.`}
        confirmLabel="Reprocesar"
        busy={busy}
        onConfirm={retryAll}
        onCancel={() => setConfirmRetry(false)}
      />
    </Dialog>
  )
}
