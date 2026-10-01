import { Fragment, useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import Dialog from '../../../shared/components/Dialog'
import StatusBadge from '../../../shared/components/StatusBadge'
import { NOTIFICATIONS_ADMIN, NOTIFICATIONS_RETRY, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { saveBlob } from '../../../shared/utils/download'
import { formatDateTime } from '../../../shared/utils/format'
import { CANCELLABLE, MESSAGE_STATUS, RETRYABLE } from '../labels'
import * as notificationsService from '../services/notificationsService'
import type { Attachment, MessageDetail } from '../types'
import HtmlPreview from './HtmlPreview'

type Action = 'retry' | 'cancel'

function sizeLabel(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// Un mensaje: destinatarios, asunto, cuerpo, adjuntos, estado y (admin) intentos.
export default function MessageDialog({ messageId, onClose, onChanged }: { messageId: string; onClose: () => void; onChanged: () => void }) {
  const can = useCanAccess()
  const isAdmin = can({ anyOf: NOTIFICATIONS_ADMIN })
  const message = useApi(() => notificationsService.getMessage(messageId), [messageId])
  const attempts = useApi(() => (isAdmin ? notificationsService.listAttempts(messageId) : Promise.resolve([])), [messageId, isAdmin])
  const [view, setView] = useState<'html' | 'text'>('html')
  const [action, setAction] = useState<Action | null>(null)
  const [busy, setBusy] = useState(false)
  const m = message.data

  const download = async (a: Attachment) => {
    try {
      const { blob, filename } = await notificationsService.downloadAttachment(messageId, a.id)
      saveBlob(blob, filename ?? a.filename)
    } catch (err) {
      toast.error(errorMessage(err)) // 410 ya purgado
    }
  }

  const run = async () => {
    if (!action) return
    setBusy(true)
    try {
      if (action === 'retry') await notificationsService.retryMessage(messageId)
      else await notificationsService.cancelMessage(messageId)
      toast.success(action === 'retry' ? 'Mensaje en cola de nuevo' : 'Mensaje cancelado')
      message.reload()
      attempts.reload()
      onChanged()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 invalid_status
    } finally {
      setBusy(false)
      setAction(null)
    }
  }

  return (
    <Dialog open wide onClose={onClose} labelledBy="message-title">
      <div className="card-header bg-transparent d-flex align-items-center gap-2">
        <h2 id="message-title" className="h5 mb-0 me-auto text-truncate">{m?.subject ?? 'Mensaje'}</h2>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} />
      </div>
      <div className="card-body">
        <AsyncState loading={message.loading} error={message.error} onRetry={message.reload} hasData={m !== undefined}>
          {m && (
            <>
              <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
                <StatusBadge {...MESSAGE_STATUS[m.status]} />
                <span className="small text-body-secondary">{MESSAGE_STATUS[m.status].help}</span>
                {can({ anyOf: NOTIFICATIONS_RETRY }) && (
                  <span className="ms-auto d-flex gap-2">
                    {RETRYABLE.includes(m.status) && (
                      <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => setAction('retry')}>
                        <i className="bi bi-arrow-repeat me-1" aria-hidden="true" />
                        Reprocesar
                      </button>
                    )}
                    {CANCELLABLE.includes(m.status) && (
                      <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setAction('cancel')}>Cancelar envío</button>
                    )}
                  </span>
                )}
              </div>

              <Details m={m} />

              <div className="d-flex align-items-center mb-2">
                <h3 className="h6 mb-0 me-auto">Contenido</h3>
                {m.body_html && m.body_text && (
                  <div className="btn-group btn-group-sm" role="group" aria-label="Formato">
                    <button type="button" className={`btn btn-outline-secondary ${view === 'html' ? 'active' : ''}`} onClick={() => setView('html')}>HTML</button>
                    <button type="button" className={`btn btn-outline-secondary ${view === 'text' ? 'active' : ''}`} onClick={() => setView('text')}>Texto</button>
                  </div>
                )}
              </div>
              {m.body_html && (view === 'html' || !m.body_text) ? (
                <HtmlPreview html={m.body_html} title={`Contenido de ${m.subject}`} />
              ) : (
                <pre className="border rounded-3 p-3 small mb-0" style={{ whiteSpace: 'pre-wrap', maxHeight: 420 }}>{m.body_text ?? ''}</pre>
              )}

              <h3 className="h6 mt-4">Adjuntos</h3>
              {m.attachments.length === 0 && <p className="small text-body-secondary">Sin adjuntos.</p>}
              <ul className="list-group mb-3">
                {m.attachments.map((a) => (
                  <li key={a.id} className="list-group-item d-flex align-items-center gap-2">
                    <i className="bi bi-paperclip" aria-hidden="true" />
                    <span className="me-auto text-truncate">{a.filename}</span>
                    <span className="small text-body-secondary">{sizeLabel(a.size_bytes)}</span>
                    {a.available ? (
                      <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => download(a)}>
                        <i className="bi bi-download" aria-hidden="true" />
                        <span className="visually-hidden">Descargar {a.filename}</span>
                      </button>
                    ) : (
                      <span className="small text-body-secondary" title="Se borra al enviarse o cancelarse el mensaje">Ya no disponible</span>
                    )}
                  </li>
                ))}
              </ul>

              {isAdmin && (
                <>
                  <h3 className="h6 mt-4">Intentos</h3>
                  <AsyncState loading={attempts.loading} error={attempts.error} onRetry={attempts.reload} hasData={attempts.data !== undefined}>
                    {attempts.data?.length === 0 ? (
                      <p className="small text-body-secondary mb-0">Aún no hubo intentos.</p>
                    ) : (
                      <div className="table-responsive border rounded-3">
                        <table className="table table-sm small align-middle mb-0">
                          <thead className="table-light">
                            <tr><th>#</th><th>Inicio</th><th>Cuenta</th><th>Resultado</th><th>Código</th><th>Respuesta</th></tr>
                          </thead>
                          <tbody>
                            {attempts.data?.map((a) => (
                              <tr key={a.id}>
                                <td>{a.attempt_number}</td>
                                <td className="text-nowrap">{formatDateTime(a.started_at)}</td>
                                <td>{a.smtp_account_name ?? '—'}</td>
                                <td>{a.outcome}{a.error_kind ? ` · ${a.error_kind}` : ''}</td>
                                <td>{a.smtp_code ?? '—'}</td>
                                <td className="text-break">{a.smtp_response ?? '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </AsyncState>
                </>
              )}
            </>
          )}
        </AsyncState>
      </div>

      <ConfirmDialog
        open={action !== null}
        title={action === 'retry' ? 'Reprocesar mensaje' : 'Cancelar mensaje'}
        message={
          action === 'retry'
            ? m?.status === 'uncertain'
              ? 'Este mensaje quizá ya llegó: si se reprocesa, el destinatario podría recibirlo dos veces.'
              : 'Vuelve a la cola con sus reintentos automáticos.'
            : 'No se enviará y se borran sus adjuntos. No se puede deshacer.'
        }
        confirmLabel={action === 'retry' ? 'Reprocesar' : 'Cancelar mensaje'}
        danger={action === 'cancel' || m?.status === 'uncertain'}
        busy={busy}
        onConfirm={run}
        onCancel={() => setAction(null)}
      />
    </Dialog>
  )
}

function Details({ m }: { m: MessageDetail }) {
  const rows: [string, string][] = [
    ['Para', m.to.join(', ') || '—'],
    ...(m.cc.length ? ([['CC', m.cc.join(', ')]] as [string, string][]) : []),
    ...(m.bcc.length ? ([['CCO', m.bcc.join(', ')]] as [string, string][]) : []),
    ...(m.reply_to ? ([['Responder a', m.reply_to]] as [string, string][]) : []),
    ['Creado', formatDateTime(m.created_at)],
    ['Enviado', m.sent_at ? formatDateTime(m.sent_at) : '—'],
    ...(m.cancel_reason ? ([['Motivo de cancelación', m.cancel_reason]] as [string, string][]) : []),
    ...(m.technical ? ([['Message-ID', m.technical.message_id_header]] as [string, string][]) : []),
  ]
  return (
    <dl className="row small mb-4">
      {rows.map(([k, v]) => (
        <Fragment key={k}>
          <dt className="col-sm-3 text-body-secondary fw-normal">{k}</dt>
          <dd className="col-sm-9 text-break">{v}</dd>
        </Fragment>
      ))}
    </dl>
  )
}
