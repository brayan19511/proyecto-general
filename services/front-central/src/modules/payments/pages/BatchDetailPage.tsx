import { Fragment, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { PAYMENTS_MANAGE, PAYMENTS_SEND, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { saveBlob } from '../../../shared/utils/download'
import { formatDate, formatDateTime } from '../../../shared/utils/format'
import DeliveryStatusPanel from '../components/DeliveryStatusPanel'
import ProviderFormModal from '../components/ProviderFormModal'
import SendBatchModal from '../components/SendBatchModal'
import { BATCH_STATUS, GROUP_STATUS } from '../labels'
import * as paymentsService from '../services/paymentsService'
import type { Batch, BatchFile, BatchGroup, Provider, ProviderInput } from '../types'

type ProviderForm = { provider: Provider | null; initial?: Partial<ProviderInput> }

// Un lote: grupos por proveedor (lo que se enviará), constancias leídas y
// acciones. En borrador los grupos se recalculan con el maestro al recargar:
// registrar un proveedor o su correo aquí mismo deja el lote listo.
export default function BatchDetailPage() {
  const { batchId = '' } = useParams()
  const navigate = useNavigate()
  const can = useCanAccess()
  const canSend = can({ anyOf: PAYMENTS_SEND })
  const canManage = can({ anyOf: PAYMENTS_MANAGE })
  const batch = useApi(() => paymentsService.getBatch(batchId), [batchId])
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [providerForm, setProviderForm] = useState<ProviderForm | null>(null)
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState<{ kind: 'discard' } | { kind: 'remove'; file: BatchFile } | null>(null)
  const [busy, setBusy] = useState(false)
  const b = batch.data
  const draft = b?.status === 'draft'

  const toggle = (i: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })

  const download = async (loader: () => Promise<{ blob: Blob; filename: string | null }>, fallback: string) => {
    try {
      const { blob, filename } = await loader()
      saveBlob(blob, filename ?? fallback)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const editProviderOf = async (g: BatchGroup) => {
    if (!g.provider_id) {
      setProviderForm({
        provider: null,
        initial: { tax_id: g.provider_tax_id ?? '', legal_name: g.pdf_holder ?? g.provider_name, commercial_names: g.pdf_holder ? [g.pdf_holder] : [] },
      })
      return
    }
    try {
      setProviderForm({ provider: await paymentsService.getProvider(g.provider_id) })
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'discard') {
        await paymentsService.discardBatch(batchId)
        toast.success('Lote descartado')
        navigate('/tesoreria/pagos')
        return
      }
      await paymentsService.removeFile(batchId, pending.file.id)
      toast.success('Constancia quitada del lote')
      batch.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  return (
    <>
      <PageHeader
        title={b?.reference ? `Lote ${b.reference}` : 'Lote de pago'}
        description={b ? `Creado ${formatDateTime(b.created_at)}${b.sent_at ? ` · enviado ${formatDateTime(b.sent_at)}` : ''}` : undefined}
        actions={
          <Link to="/tesoreria/pagos" className="btn btn-outline-secondary">
            <i className="bi bi-arrow-left me-1" aria-hidden="true" />
            Lotes
          </Link>
        }
      />
      <AsyncState loading={batch.loading} error={batch.error} onRetry={batch.reload} hasData={b !== undefined}>
        {b && (
          <>
            <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
              <StatusBadge {...BATCH_STATUS[b.status]} />
              <span className="badge text-bg-light border fw-normal">{b.counts.parsed}/{b.counts.files} leídas</span>
              {b.counts.errors > 0 && <span className="badge text-bg-danger fw-normal">{b.counts.errors} con error</span>}
              <span className="badge text-bg-light border fw-normal">{b.counts.groups} proveedores</span>
              {b.counts.missing_provider > 0 && <span className="badge text-bg-danger fw-normal">{b.counts.missing_provider} sin proveedor</span>}
              {b.counts.missing_email > 0 && <span className="badge text-bg-warning fw-normal">{b.counts.missing_email} sin correo</span>}
              <span className="ms-auto d-flex flex-wrap gap-2">
                <button type="button" className="btn btn-sm btn-outline-secondary" onClick={batch.reload} title="Recalcular con el maestro actual">
                  <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
                  Actualizar
                </button>
                {canSend && b.counts.parsed > 0 && (
                  <button type="button" className="btn btn-sm btn-outline-secondary"
                    onClick={() => download(() => paymentsService.downloadZip(b.id), 'constancias_renombradas.zip')}>
                    <i className="bi bi-file-earmark-zip me-1" aria-hidden="true" />
                    ZIP renombrado
                  </button>
                )}
                {canSend && draft && (
                  <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'discard' })}>Descartar</button>
                )}
                {canSend && (b.ready_to_send || b.status === 'sending') && (
                  <button type="button" className="btn btn-sm btn-primary" onClick={() => setSending(true)}>
                    <i className="bi bi-send me-1" aria-hidden="true" />
                    {b.status === 'sending' ? 'Reintentar envío' : 'Enviar avisos'}
                  </button>
                )}
              </span>
            </div>

            {draft && !b.ready_to_send && (
              <div className="alert alert-warning small">
                Para enviar, cada grupo debe estar "Listo" y ninguna constancia con error
                {canManage ? ': registra los proveedores o correos que faltan, o quita las constancias con error.' : '.'}
              </div>
            )}
            {b.status === 'sending' && (
              <div className="alert alert-info small">
                El envío no terminó de confirmarse (p. ej. notificaciones no respondió). Reintentar no duplica correos.
              </div>
            )}

            {b.status !== 'draft' && b.notification_dispatch_id && <DeliveryStatusPanel batchId={b.id} />}

            <h2 className="h6 mt-4">Proveedores</h2>
            <GroupsTable batch={b} expanded={expanded} toggle={toggle} canManage={canManage && draft} onEditProvider={editProviderOf} />

            <h2 className="h6 mt-4">Constancias</h2>
            <FilesTable batch={b} canRemove={canSend && draft} onRemove={(file) => setPending({ kind: 'remove', file })}
              onDownload={(f) => download(() => paymentsService.downloadFile(b.id, f.id), f.original_filename)} />
          </>
        )}
      </AsyncState>

      {providerForm && (
        <ProviderFormModal provider={providerForm.provider} initial={providerForm.initial}
          onClose={() => setProviderForm(null)} onSaved={batch.reload} />
      )}
      {sending && b && <SendBatchModal batch={b} onClose={() => setSending(false)} onSent={batch.reload} />}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'discard' ? 'Descartar lote' : 'Quitar constancia'}
        message={pending?.kind === 'discard'
          ? 'El borrador deja de aparecer en la lista. No se envía nada.'
          : `${pending?.kind === 'remove' ? pending.file.original_filename : ''} deja de formar parte del lote.`}
        confirmLabel={pending?.kind === 'discard' ? 'Descartar' : 'Quitar'}
        danger
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}

type GroupsTableProps = {
  batch: Batch
  expanded: Set<number>
  toggle: (i: number) => void
  canManage: boolean
  onEditProvider: (g: BatchGroup) => void
}

function GroupsTable({ batch, expanded, toggle, canManage, onEditProvider }: GroupsTableProps) {
  if (batch.groups.length === 0) return <p className="text-body-secondary small">Ninguna constancia leída todavía.</p>
  return (
    <div className="table-responsive border rounded-3">
      <table className="table align-middle mb-0">
        <thead className="table-light">
          <tr><th /><th>Proveedor</th><th>Correos</th><th className="text-end">Pagos</th><th className="text-end">Total</th><th>Estado</th><th /></tr>
        </thead>
        <tbody>
          {batch.groups.map((g, i) => (
            <Fragment key={`${g.provider_id ?? g.provider_name}-${i}`}>
              <tr>
                <td>
                  <button type="button" className="btn btn-sm btn-link p-0" aria-expanded={expanded.has(i)} onClick={() => toggle(i)}
                    aria-label={`Ver pagos de ${g.provider_name}`}>
                    <i className={`bi bi-chevron-${expanded.has(i) ? 'down' : 'right'}`} aria-hidden="true" />
                  </button>
                </td>
                <td>
                  <div>{g.provider_name}</div>
                  <div className="small text-body-secondary">
                    {g.provider_tax_id && <span className="font-monospace">{g.provider_tax_id}</span>}
                    {g.pdf_holder && g.pdf_holder !== g.provider_name && <span> · en constancia: {g.pdf_holder}</span>}
                  </div>
                </td>
                <td className="small">{g.payment_emails.join(', ') || '—'}</td>
                <td className="text-end">{g.payment_count}</td>
                <td className="text-end text-nowrap font-monospace small">
                  {g.totals.map((t) => <div key={t.currency}>{t.symbol} {t.total}</div>)}
                </td>
                <td><StatusBadge {...GROUP_STATUS[g.status]} /></td>
                <td className="text-end text-nowrap">
                  {canManage && g.status === 'MISSING_PROVIDER' && (
                    <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => onEditProvider(g)}>Registrar proveedor</button>
                  )}
                  {canManage && g.status === 'MISSING_PAYMENT_EMAIL' && (
                    <button type="button" className="btn btn-sm btn-outline-primary" onClick={() => onEditProvider(g)}>Agregar correo</button>
                  )}
                </td>
              </tr>
              {expanded.has(i) && (
                <tr>
                  <td />
                  <td colSpan={6} className="bg-body-tertiary">
                    <table className="table table-sm small mb-0 bg-transparent">
                      <thead>
                        <tr><th>Archivo renombrado</th><th>Cuenta</th><th>Referencia</th><th>Fecha</th><th className="text-end">Monto</th></tr>
                      </thead>
                      <tbody>
                        {g.payments.map((p) => (
                          <tr key={p.file_id}>
                            <td className="text-break">{p.suggested_filename}</td>
                            <td className="font-monospace">{p.account ?? '—'}</td>
                            <td>{p.reference ?? '—'}</td>
                            <td className="text-nowrap">{p.process_date ?? '—'}</td>
                            <td className="text-end font-monospace text-nowrap">{p.currency} {p.amount}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

type FilesTableProps = {
  batch: Batch
  canRemove: boolean
  onRemove: (f: BatchFile) => void
  onDownload: (f: BatchFile) => void
}

function FilesTable({ batch, canRemove, onRemove, onDownload }: FilesTableProps) {
  return (
    <div className="table-responsive border rounded-3">
      <table className="table align-middle small mb-0">
        <thead className="table-light">
          <tr><th>#</th><th>Archivo</th><th>Titular</th><th>RUC / DNI</th><th>Fecha</th><th className="text-end">Monto</th><th>Lectura</th><th /></tr>
        </thead>
        <tbody>
          {batch.files.map((f) => (
            <tr key={f.id}>
              <td className="text-body-secondary">{f.sequence}</td>
              <td className="text-break">
                {f.original_filename}
                {f.already_sent_in_batch_id && (
                  <div>
                    <Link to={`/tesoreria/pagos/${f.already_sent_in_batch_id}`} className="text-warning-emphasis">
                      <i className="bi bi-exclamation-triangle me-1" aria-hidden="true" />
                      {f.already_sent_match === 'data'
                        ? 'Posible pago repetido: mismos datos que uno ya enviado'
                        : 'Este mismo PDF ya se envió en otro lote'}
                    </Link>
                  </div>
                )}
              </td>
              <td>{f.beneficiary_name ?? '—'}</td>
              <td className="font-monospace">{f.beneficiary_tax_id ?? '—'}</td>
              <td className="text-nowrap">{f.operation_date ? formatDate(f.operation_date) : '—'}</td>
              <td className="text-end font-monospace text-nowrap">{f.amount ? `${f.currency ?? ''} ${f.amount}` : '—'}</td>
              <td>
                {f.parse_status === 'parsed' ? (
                  <StatusBadge tone="success" label={f.used_ocr ? 'Leída (OCR)' : 'Leída'} />
                ) : (
                  <span title={f.parse_error ?? ''}><StatusBadge tone="danger" label="Error" /></span>
                )}
                {f.parse_error && <div className="text-danger mt-1">{f.parse_error}</div>}
              </td>
              <td className="text-end text-nowrap">
                <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => onDownload(f)} title="Descargar PDF">
                  <i className="bi bi-download" aria-hidden="true" />
                  <span className="visually-hidden">Descargar {f.original_filename}</span>
                </button>
                {canRemove && (
                  <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => onRemove(f)} title="Quitar del lote">
                    <i className="bi bi-x-lg" aria-hidden="true" />
                    <span className="visually-hidden">Quitar {f.original_filename}</span>
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
