import AsyncState from '../../../shared/components/AsyncState'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import { DISPATCH_STATUS, MESSAGE_STATUS } from '../../notifications/labels'
import type { DispatchStatus, MessageStatus } from '../../notifications/types'
import * as paymentsService from '../services/paymentsService'

// Estado de los correos del lote, consultado a notificaciones en el momento.
// Exige además notifications.view: sin él se muestra el error de permiso.
export default function DeliveryStatusPanel({ batchId }: { batchId: string }) {
  const status = useApi(() => paymentsService.getDeliveryStatus(batchId), [batchId])
  const s = status.data

  return (
    <div className="card mb-3">
      <div className="card-header bg-transparent d-flex align-items-center gap-2">
        <h2 className="h6 mb-0 me-auto">Estado de los correos</h2>
        {s && DISPATCH_STATUS[s.status as DispatchStatus] && <StatusBadge {...DISPATCH_STATUS[s.status as DispatchStatus]} />}
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={status.reload} title="Actualizar">
          <i className="bi bi-arrow-clockwise" aria-hidden="true" />
          <span className="visually-hidden">Actualizar estado</span>
        </button>
      </div>
      <div className="card-body">
        <AsyncState loading={status.loading} error={status.error} onRetry={status.reload} hasData={s !== undefined}>
          {s && (
            <ul className="list-group list-group-flush">
              {s.deliveries.map((d) => {
                const label = d.status ? MESSAGE_STATUS[d.status as MessageStatus] : undefined
                return (
                  <li key={d.delivery_id} className="list-group-item px-0 d-flex flex-wrap align-items-center gap-2">
                    <span className="me-auto">
                      {d.legal_name}
                      <span className="small text-body-secondary"> · {d.payment_emails.join(', ')}</span>
                    </span>
                    {d.sent_at && <span className="small text-body-secondary">{formatDateTime(d.sent_at)}</span>}
                    {label ? <StatusBadge tone={label.tone} label={label.label} /> : <StatusBadge tone="secondary" label={d.status ?? 'Sin estado'} />}
                  </li>
                )
              })}
            </ul>
          )}
        </AsyncState>
        <p className="small text-body-secondary mb-0 mt-2">Para reprocesar un correo fallido, ábrelo en Tesorería › Correos enviados.</p>
      </div>
    </div>
  )
}
