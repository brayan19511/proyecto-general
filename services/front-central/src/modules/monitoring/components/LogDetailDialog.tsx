import AsyncState from '../../../shared/components/AsyncState'
import Dialog from '../../../shared/components/Dialog'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import { formatDuration } from '../logLabels'
import * as logsService from '../services/logsService'
import type { LogServiceKey } from '../services/logsService'
import { HttpStatus, OutcomeBadge } from './LogBadges'

type LogDetailDialogProps = {
  service: LogServiceKey
  logId: string
  userEmail: (userId: string | null) => string
  onTrace: (traceId: string) => void
  onClose: () => void
}

const KIND_LABEL: Record<string, string> = {
  request: 'Solicitud',
  response: 'Respuesta',
  error: 'Error',
  message: 'Mensaje',
}

// Una solicitud en un servicio: cabecera, detalles (request/response/error con
// datos ya enmascarados por el servicio) y pasos internos.
export default function LogDetailDialog({ service, logId, userEmail, onTrace, onClose }: LogDetailDialogProps) {
  const query = useApi(() => logsService.getLog(service, logId), [service, logId])
  const log = query.data
  const serviceLabel = logsService.findLogService(service)?.label ?? service

  return (
    <Dialog open wide onClose={onClose} labelledBy="log-title">
      <div className="card-header bg-transparent d-flex align-items-center gap-2">
        <h2 id="log-title" className="h5 mb-0 me-auto">Log de {serviceLabel}</h2>
        {log && (
          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => onTrace(log.trace_id)}>
            <i className="bi bi-diagram-2 me-1" aria-hidden="true" />
            Ver traza completa
          </button>
        )}
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} />
      </div>

      <div className="card-body">
        <AsyncState loading={query.loading} error={query.error} onRetry={query.reload} hasData={log !== undefined}>
          {log && (
            <>
              <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
                <span className="badge text-bg-light border">{log.method}</span>
                <span className="font-monospace">{log.path}</span>
                <HttpStatus code={log.status_code} />
                <OutcomeBadge outcome={log.outcome} />
              </div>

              <dl className="row small mb-4">
                <dt className="col-sm-3 text-body-secondary fw-normal">Inicio</dt>
                <dd className="col-sm-9">{formatDateTime(log.started_at)} · {formatDuration(log.duration_ms)}</dd>
                <dt className="col-sm-3 text-body-secondary fw-normal">Usuario</dt>
                <dd className="col-sm-9">{userEmail(log.user_id)}</dd>
                <dt className="col-sm-3 text-body-secondary fw-normal">IP</dt>
                <dd className="col-sm-9 font-monospace">{log.ip_address ?? '—'}</dd>
                <dt className="col-sm-3 text-body-secondary fw-normal">Navegador / cliente</dt>
                <dd className="col-sm-9 text-break">{log.user_agent ?? '—'}</dd>
                <dt className="col-sm-3 text-body-secondary fw-normal">Empresa (id)</dt>
                <dd className="col-sm-9 font-monospace">{log.company_id ?? '—'}</dd>
                <dt className="col-sm-3 text-body-secondary fw-normal">Trace id</dt>
                <dd className="col-sm-9 font-monospace mb-0">{log.trace_id}</dd>
              </dl>

              <h3 className="h6">Detalles</h3>
              {log.details.length === 0 && <p className="small text-body-secondary">Sin detalles registrados.</p>}
              {log.details.map((d, i) => (
                <div key={i} className="border rounded-3 p-2 mb-2">
                  <div className="d-flex flex-wrap align-items-center gap-2 small mb-1">
                    <span className={`badge ${d.kind === 'error' ? 'text-bg-danger' : 'text-bg-secondary'}`}>
                      {KIND_LABEL[d.kind] ?? d.kind}
                    </span>
                    <span className="text-body-secondary">{d.level} · {formatDateTime(d.created_at)}</span>
                    {d.message && <span>{d.message}</span>}
                  </div>
                  {d.data && (
                    <pre className="small bg-body-tertiary rounded-2 p-2 mb-0" style={{ maxHeight: 280 }}>
                      {JSON.stringify(d.data, null, 2)}
                    </pre>
                  )}
                </div>
              ))}

              <h3 className="h6 mt-4">Pasos</h3>
              {log.steps.length === 0 ? (
                <p className="small text-body-secondary mb-0">Sin pasos registrados.</p>
              ) : (
                <div className="table-responsive border rounded-3">
                  <table className="table table-sm mb-0 small">
                    <thead className="table-light">
                      <tr><th>Paso</th><th>Fase</th><th>Mensaje</th><th className="text-end">Duración</th></tr>
                    </thead>
                    <tbody>
                      {log.steps.map((s, i) => (
                        <tr key={`${s.step_id}-${i}`}>
                          <td className="font-monospace">{s.name}</td>
                          <td>{s.phase}</td>
                          <td>{s.message ?? '—'}</td>
                          <td className="text-end text-nowrap">{formatDuration(s.duration_ms)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </AsyncState>
      </div>
    </Dialog>
  )
}
