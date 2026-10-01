import AsyncState from '../../../shared/components/AsyncState'
import Dialog from '../../../shared/components/Dialog'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import { formatDuration } from '../logLabels'
import * as logsService from '../services/logsService'
import type { LogServiceKey } from '../services/logsService'
import { HttpStatus, OutcomeBadge } from './LogBadges'

type TraceDialogProps = {
  traceId: string
  onOpenLog: (service: LogServiceKey, logId: string) => void
  onClose: () => void
}

// Una solicitud vista en todos los servicios, en orden de tiempo: la central
// recibe, reenvía; el servicio de destino consulta a auth, etc.
export default function TraceDialog({ traceId, onOpenLog, onClose }: TraceDialogProps) {
  const query = useApi(() => logsService.getTrace(traceId), [traceId])
  const entries = query.data?.entries ?? []
  const failed = query.data?.failed ?? []

  return (
    <Dialog open wide onClose={onClose} labelledBy="trace-title">
      <div className="card-header bg-transparent d-flex align-items-center gap-2">
        <div className="me-auto">
          <h2 id="trace-title" className="h5 mb-0">Traza completa</h2>
          <div className="small text-body-secondary font-monospace">{traceId}</div>
        </div>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} />
      </div>
      <div className="card-body">
        {failed.length > 0 && (
          <div className="alert alert-warning py-2 small">No se pudieron leer los logs de: {failed.join(', ')}.</div>
        )}
        <AsyncState loading={query.loading} error={query.error} onRetry={query.reload} hasData={query.data !== undefined}>
          {entries.length === 0 ? (
            <p className="text-body-secondary mb-0">No hay registros con este trace id.</p>
          ) : (
            <div className="table-responsive border rounded-3">
              <table className="table table-sm table-hover align-middle mb-0">
                <thead className="table-light">
                  <tr><th>Inicio</th><th>Servicio</th><th>Operación</th><th>HTTP</th><th>Resultado</th><th className="text-end">Duración</th></tr>
                </thead>
                <tbody>
                  {entries.map(({ service, log }) => (
                    <tr key={`${service}-${log.id}`}>
                      <td className="text-nowrap small">{formatDateTime(log.started_at)}</td>
                      <td>{logsService.findLogService(service)?.label}</td>
                      <td>
                        <button type="button" className="btn btn-link p-0 text-start text-decoration-none" onClick={() => onOpenLog(service, log.id)}>
                          <span className="badge text-bg-light border me-2">{log.method}</span>
                          <span className="font-monospace small">{log.path}</span>
                        </button>
                      </td>
                      <td><HttpStatus code={log.status_code} /></td>
                      <td><OutcomeBadge outcome={log.outcome} /></td>
                      <td className="text-end text-nowrap">{formatDuration(log.duration_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncState>
      </div>
    </Dialog>
  )
}
