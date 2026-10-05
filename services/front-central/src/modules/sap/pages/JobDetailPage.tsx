import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { SAP_EXECUTE, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { useInterval } from '../../../shared/hooks/useInterval'
import { toast } from '../../../shared/stores/toastStore'
import { formatDateTime } from '../../../shared/utils/format'
import CredentialsModal from '../components/CredentialsModal'
import JsonDialog, { type JsonSection } from '../components/JsonDialog'
import RevealCredentialsDialog from '../components/RevealCredentialsDialog'
import { EVENT_LABEL, isOpen, ITEM_STATUS, JOB_STATUS, KIND_LABEL } from '../labels'
import * as sapService from '../services/sapService'
import type { ItemStatus, Job, JobItem } from '../types'

// Detalle de un trabajo: resumen, acciones según el estado, ítems con el
// resultado de SAP e historial. Se actualiza cada 3 s mientras está abierto.
export default function JobDetailPage() {
  const { jobId = '' } = useParams()
  const canExecute = useCanAccess()({ anyOf: SAP_EXECUTE })
  const job = useApi(() => sapService.getJob(jobId), [jobId])
  const [itemStatus, setItemStatus] = useState<ItemStatus | ''>('')
  const [draftRef, setDraftRef] = useState('')
  const [reference, setReference] = useState('')
  const [offset, setOffset] = useState(0)
  const items = useApi(() => sapService.listItems(jobId, { status: itemStatus, reference }, offset), [jobId, itemStatus, reference, offset])
  const events = useApi(() => sapService.listEvents(jobId), [jobId])
  const [credentials, setCredentials] = useState<'enqueue' | 'resume' | null>(null)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [revealing, setRevealing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [json, setJson] = useState<{ title: string; sections: JsonSection[] } | null>(null)
  const [downloading, setDownloading] = useState(false)

  const openItem = async (item: JobItem) => {
    try {
      const detail = await sapService.getItem(jobId, item.seq)
      setJson({
        title: `Ítem #${detail.seq} · ${detail.reference}`,
        sections: [
          { title: 'Enviado a SAP', value: detail.request, note: detail.request ? `${detail.request.method} …/${detail.request.path}` : 'Aún no se envió.' },
          {
            title: 'Respuesta de SAP',
            value: detail.response,
            note: detail.response ? `HTTP ${detail.response.status}` : detail.status === 'uncertain' ? 'Sin respuesta: el resultado es incierto, revísalo en SAP.' : 'Sin respuesta todavía.',
          },
        ],
      })
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }
  const download = async () => {
    setDownloading(true)
    try {
      await sapService.exportItems(jobId)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setDownloading(false)
    }
  }

  const reloadAll = () => { job.reload(); items.reload(); events.reload() }
  useInterval(job.data ? isOpen(job.data.status) : false, reloadAll, 3000)

  // Se recarga el trabajo (no solo se reemplaza) para traer can_view_credentials actualizado.
  const updated = (next: Job) => { job.setData({ ...next, can_view_credentials: job.data?.can_view_credentials ?? false }); reloadAll() }
  const cancel = async () => {
    setBusy(true)
    try {
      updated(await sapService.cancel(jobId))
      toast.success('Cancelación registrada')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setConfirmCancel(false)
    }
  }
  const searchRef = (event: FormEvent) => {
    event.preventDefault()
    setReference(draftRef.trim())
    setOffset(0)
  }

  const j = job.data
  const columns: Column<JobItem>[] = [
    { header: '#', className: 'small text-body-secondary', render: (i) => i.seq },
    { header: j?.kind === 'reconciliation' ? 'ReconNum' : 'DocEntry', className: 'font-monospace', render: (i) => i.reference },
    { header: 'Estado', render: (i) => <StatusBadge tone={ITEM_STATUS[i.status].tone} label={ITEM_STATUS[i.status].label} /> },
    { header: 'Respuesta de SAP', className: 'small', render: (i) => i.sap_error ?? (i.http_status ? `HTTP ${i.http_status}` : '—') },
    { header: 'Fin', className: 'small text-nowrap text-body-secondary', render: (i) => (i.finished_at ? formatDateTime(i.finished_at) : '—') },
    {
      header: '',
      className: 'text-end',
      render: (i) => (
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => openItem(i)} title="Ver lo enviado y la respuesta de SAP">
          <i className="bi bi-braces" aria-hidden="true" /><span className="ms-1">JSON</span>
        </button>
      ),
    },
  ]

  return (
    <AsyncState loading={job.loading} error={job.error} onRetry={job.reload} hasData={j !== undefined}>
      {j && (
        <>
          <PageHeader
            title={`${KIND_LABEL[j.kind]} · ${j.company_db}`}
            description={j.kind === 'document_action' ? `${j.entity}(DocEntry)/${j.action}` : `${j.parameters.filename ?? ''} · fecha ${j.parameters.recon_date ?? ''}`}
            actions={
              <>
                <Link to="/sap/trabajos" className="btn btn-outline-secondary">Volver</Link>
                <button type="button" className="btn btn-outline-secondary" title="Datos con que se registró el trabajo"
                  onClick={() => setJson({ title: 'Cabecera del trabajo', sections: [{ title: 'Trabajo', value: j, note: j.trace_id ? `trace_id ${j.trace_id}: búscalo en Monitoreo › Actividad y logs.` : undefined }] })}>
                  <i className="bi bi-braces me-1" aria-hidden="true" />Cabecera
                </button>
                <button type="button" className="btn btn-outline-secondary" disabled={downloading} onClick={download} title="CSV con todos los ítems y la respuesta de SAP">
                  {downloading ? <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" /> : <i className="bi bi-download me-1" aria-hidden="true" />}
                  Descargar CSV
                </button>
                {j.can_view_credentials && (
                  <button type="button" className="btn btn-outline-warning" onClick={() => setRevealing(true)}>
                    <i className="bi bi-key me-1" aria-hidden="true" />Ver credenciales
                  </button>
                )}
                {canExecute && j.status === 'failed' && <button type="button" className="btn btn-primary" onClick={() => setCredentials('resume')}>Reanudar</button>}
                {canExecute && ['draft', 'queued', 'running', 'failed'].includes(j.status) && !j.cancel_requested_at && (
                  <button type="button" className="btn btn-outline-danger" onClick={() => setConfirmCancel(true)}>Cancelar</button>
                )}
                {canExecute && j.status === 'draft' && (
                  <button type="button" className="btn btn-danger" onClick={() => setCredentials('enqueue')}>
                    <i className="bi bi-play-fill me-1" aria-hidden="true" />Ejecutar en SAP
                  </button>
                )}
              </>
            }
          />
          <Summary job={j} />

          <h2 className="h6 mt-4">Ítems</h2>
          <form className="d-flex flex-wrap gap-2 mb-2" onSubmit={searchRef}>
            <select className="form-select form-select-sm w-auto" aria-label="Estado del ítem" value={itemStatus}
              onChange={(e) => { setItemStatus(e.target.value as ItemStatus | ''); setOffset(0) }}>
              <option value="">Todos</option>
              {(Object.keys(ITEM_STATUS) as ItemStatus[]).map((s) => <option key={s} value={s}>{ITEM_STATUS[s].label}</option>)}
            </select>
            <input className="form-control form-control-sm" style={{ maxWidth: 200 }} placeholder={j.kind === 'reconciliation' ? 'ReconNum' : 'DocEntry'}
              aria-label="Buscar ítem" value={draftRef} onChange={(e) => setDraftRef(e.target.value)} />
            <button type="submit" className="btn btn-sm btn-outline-primary">Buscar</button>
          </form>
          <AsyncState loading={items.loading} error={items.error} onRetry={items.reload} hasData={items.data !== undefined}>
            <DataTable columns={columns} rows={items.data?.items ?? []} rowKey={(i) => String(i.seq)} emptyMessage="Sin ítems con ese filtro." />
            <Pager offset={offset} limit={sapService.PAGE_SIZE} count={items.data?.items.length ?? 0} total={items.data?.total} onChange={setOffset} />
          </AsyncState>

          <h2 className="h6 mt-4">Historial</h2>
          <ul className="list-unstyled small mb-0">
            {(events.data ?? []).map((e, index) => (
              <li key={index} className="mb-1">
                <span className="text-body-secondary">{formatDateTime(e.created_at)}</span>
                {' · '}{EVENT_LABEL[e.action] ?? e.action}
                {' · '}<span className="text-body-secondary" title={e.actor}>{e.actor_kind === 'system' ? 'worker' : e.actor.slice(0, 8)}</span>
                {typeof e.details.reason === 'string' && <span className="text-danger"> · {e.details.reason}</span>}
              </li>
            ))}
          </ul>

          {credentials && <CredentialsModal job={j} mode={credentials} onClose={() => setCredentials(null)} onDone={updated} />}
          {json && <JsonDialog title={json.title} sections={json.sections} onClose={() => setJson(null)} />}
          {revealing &&<RevealCredentialsDialog jobId={j.id} onClose={() => { setRevealing(false); events.reload() }} />}
          <ConfirmDialog
            open={confirmCancel}
            title="Cancelar trabajo"
            message={j.status === 'running'
              ? 'El worker se detiene antes del próximo ítem. Lo ya enviado a SAP no se deshace.'
              : 'Los ítems pendientes se cancelan y el trabajo no se ejecutará. Lo ya enviado a SAP no se deshace.'}
            confirmLabel="Cancelar trabajo"
            danger
            busy={busy}
            onConfirm={cancel}
            onCancel={() => setConfirmCancel(false)}
          />
        </>
      )}
    </AsyncState>
  )
}

function Summary({ job }: { job: Job }) {
  const done = job.succeeded_items + job.failed_items + job.uncertain_items + job.cancelled_items
  const percent = job.total_items ? Math.round((done / job.total_items) * 100) : 0
  const status = JOB_STATUS[job.status]
  return (
    <div className="border rounded-3 p-3">
      <div className="d-flex flex-wrap align-items-center gap-3 mb-2">
        <StatusBadge tone={status.tone} label={job.cancel_requested_at && job.status === 'running' ? 'Cancelando…' : status.label} />
        <span className="small"><strong>{job.total_items}</strong> ítems</span>
        <span className="small text-success"><strong>{job.succeeded_items}</strong> correctos</span>
        <span className="small text-danger"><strong>{job.failed_items}</strong> con error de SAP</span>
        <span className="small text-warning-emphasis"><strong>{job.uncertain_items}</strong> inciertos</span>
        {job.cancelled_items > 0 && <span className="small"><strong>{job.cancelled_items}</strong> cancelados</span>}
        {job.sap_user && <span className="small text-body-secondary">Usuario SAP: {job.sap_user}</span>}
      </div>
      <div className="progress" role="progressbar" aria-label="Avance" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} style={{ height: 8 }}>
        <div className="progress-bar" style={{ width: `${percent}%` }} />
      </div>
      {job.status === 'draft' && <p className="small text-body-secondary mt-2 mb-0">Borrador: revisa los ítems y ejecútalo con tu usuario SAP. Aún no se envió nada a SAP.</p>}
      {job.error_message && <p className="small text-danger mt-2 mb-0">{job.error_message}</p>}
      {job.uncertain_items > 0 && (
        <p className="small text-warning-emphasis mt-2 mb-0">
          Los ítems inciertos se enviaron a SAP pero no hubo respuesta: revisa en SAP si se aplicaron. No se repiten automáticamente.
        </p>
      )}
    </div>
  )
}
