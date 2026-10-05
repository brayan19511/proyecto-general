import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { SAP_EXECUTE, useCanAccess } from '../../../shared/auth/access'
import { useApi } from '../../../shared/hooks/useApi'
import { useInterval } from '../../../shared/hooks/useInterval'
import { formatDateTime } from '../../../shared/utils/format'
import NewJobModal from '../components/NewJobModal'
import { isOpen, JOB_STATUS, KIND_LABEL } from '../labels'
import * as sapService from '../services/sapService'
import type { JobKind, JobListItem, JobStatus } from '../types'

// SAP › Operaciones masivas: acciones sobre documentos y conciliaciones internas
// por Service Layer. Ver: sap_operations.view; crear y ejecutar: execute.
export default function JobsPage() {
  const canExecute = useCanAccess()({ anyOf: SAP_EXECUTE })
  const navigate = useNavigate()
  const [status, setStatus] = useState<JobStatus | ''>('')
  const [kind, setKind] = useState<JobKind | ''>('')
  const [offset, setOffset] = useState(0)
  const jobs = useApi(() => sapService.listJobs({ status, kind }, offset), [status, kind, offset])
  const [creating, setCreating] = useState<JobKind | null>(null)
  // Mientras haya trabajos en cola o en proceso, se actualiza cada 5 s.
  useInterval((jobs.data?.items ?? []).some((j) => isOpen(j.status)), jobs.reload, 5000)

  const columns: Column<JobListItem>[] = [
    { header: 'Creado', className: 'small text-nowrap', render: (j) => formatDateTime(j.created_at) },
    { header: 'Tipo', className: 'text-nowrap', render: (j) => KIND_LABEL[j.kind] },
    {
      header: 'Detalle',
      className: 'small',
      render: (j) => (
        <>
          <span className="font-monospace">{j.company_db}</span>
          {' · '}
          {j.kind === 'document_action' ? <span className="font-monospace">{j.entity}/{j.action}</span> : j.parameters.filename}
        </>
      ),
    },
    { header: 'Estado', render: (j) => <StatusBadge tone={JOB_STATUS[j.status].tone} label={JOB_STATUS[j.status].label} /> },
    {
      header: 'Avance',
      className: 'small text-nowrap',
      render: (j) => {
        const done = j.succeeded_items + j.failed_items + j.uncertain_items + j.cancelled_items
        return `${done} / ${j.total_items}${j.failed_items + j.uncertain_items ? ` · ${j.failed_items + j.uncertain_items} con problemas` : ''}`
      },
    },
    { header: '', className: 'text-end', render: (j) => <Link className="btn btn-sm btn-outline-primary" to={`/sap/trabajos/${j.id}`}>Abrir</Link> },
  ]

  return (
    <>
      <PageHeader
        title="Operaciones masivas"
        description="Acciones sobre documentos y conciliaciones internas en SAP, ejecutadas por el worker con tu usuario SAP."
        actions={canExecute && (
          <>
            <button type="button" className="btn btn-outline-primary" onClick={() => setCreating('reconciliation')}>
              <i className="bi bi-arrow-left-right me-1" aria-hidden="true" />Conciliación
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setCreating('document_action')}>
              <i className="bi bi-file-earmark-x me-1" aria-hidden="true" />Acción sobre documentos
            </button>
          </>
        )}
      />
      <div className="d-flex flex-wrap gap-2 mb-3">
        <select className="form-select form-select-sm w-auto" aria-label="Tipo" value={kind}
          onChange={(e) => { setKind(e.target.value as JobKind | ''); setOffset(0) }}>
          <option value="">Todos los tipos</option>
          {(Object.keys(KIND_LABEL) as JobKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
        <select className="form-select form-select-sm w-auto" aria-label="Estado" value={status}
          onChange={(e) => { setStatus(e.target.value as JobStatus | ''); setOffset(0) }}>
          <option value="">Todos los estados</option>
          {(Object.keys(JOB_STATUS) as JobStatus[]).map((s) => <option key={s} value={s}>{JOB_STATUS[s].label}</option>)}
        </select>
      </div>
      <AsyncState loading={jobs.loading} error={jobs.error} onRetry={jobs.reload} hasData={jobs.data !== undefined}>
        <DataTable columns={columns} rows={jobs.data?.items ?? []} rowKey={(j) => j.id} emptyMessage="Aún no hay trabajos." />
        <Pager offset={offset} limit={sapService.PAGE_SIZE} count={jobs.data?.items.length ?? 0} total={jobs.data?.total} onChange={setOffset} />
      </AsyncState>
      {creating && <NewJobModal kind={creating} onClose={() => setCreating(null)} onCreated={(job) => navigate(`/sap/trabajos/${job.id}`)} />}
    </>
  )
}
