import { useState } from 'react'
import { LEDGER_UPDATE, useCanAccess } from '../../../shared/auth/access'
import AsyncState from '../../../shared/components/AsyncState'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useApi } from '../../../shared/hooks/useApi'
import { useInterval } from '../../../shared/hooks/useInterval'
import { formatDate, formatDateTime } from '../../../shared/utils/format'
import * as rulesService from '../services/rulesService'
import { RUN_STATUS } from '../syncLabels'
import type { ClassificationRun } from '../types'
import ReclassifyModal from './ReclassifyModal'

const numberFormat = new Intl.NumberFormat('es-PE')
const POLL_MS = 5000

const COLUMNS: Column<ClassificationRun>[] = [
  { header: 'Creada', className: 'text-nowrap', render: (r) => formatDateTime(r.created_at) },
  { header: 'Motivo', render: (r) => (r.reason === 'rule_change' ? 'Cambio de regla' : 'Manual') },
  {
    header: 'Rango',
    className: 'text-nowrap',
    render: (r) => (r.date_from && r.date_to ? `${formatDate(r.date_from)} – ${formatDate(r.date_to)}` : 'Todas las líneas'),
  },
  { header: 'Estado', render: (r) => <StatusBadge {...RUN_STATUS[r.status]} /> },
  {
    header: 'Líneas',
    className: 'text-nowrap small',
    render: (r) => `${numberFormat.format(r.rows_checked)} revisadas · ${numberFormat.format(r.rows_changed)} cambiaron`,
  },
  { header: 'Fin', className: 'text-nowrap', render: (r) => (r.finished_at ? formatDateTime(r.finished_at) : '—') },
  { header: 'Error', render: (r) => (r.safe_error ? <span className="small text-danger-emphasis">{r.safe_error}</span> : '—') },
]

// Reclasificaciones que hace el worker (por cambios de reglas o manuales).
export default function ClassificationRunsTab() {
  const canEdit = useCanAccess()({ anyOf: LEDGER_UPDATE })
  const [offset, setOffset] = useState(0)
  const [showModal, setShowModal] = useState(false)
  const runs = useApi(() => rulesService.listClassificationRuns(offset), [offset])

  // Mientras alguna esté abierta, se consulta su avance.
  const hasOpen = (runs.data ?? []).some((r) => r.status === 'pending' || r.status === 'running')
  useInterval(hasOpen, runs.reload, POLL_MS)

  return (
    <>
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
        <p className="text-body-secondary mb-0">Cada cambio de regla registra una reclasificación automática.</p>
        <div className="d-flex gap-2">
          <button type="button" className="btn btn-outline-secondary" onClick={runs.reload}>
            <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
            Actualizar
          </button>
          {canEdit && (
            <button type="button" className="btn btn-primary" onClick={() => setShowModal(true)}>
              <i className="bi bi-shuffle me-1" aria-hidden="true" />
              Reclasificar
            </button>
          )}
        </div>
      </div>

      {hasOpen && (
        <div className="alert alert-info d-flex align-items-center gap-2 py-2" role="status">
          <span className="spinner-border spinner-border-sm" aria-hidden="true" />
          Hay reclasificaciones en proceso. El avance se actualiza solo.
        </div>
      )}

      <AsyncState loading={runs.loading} error={runs.error} onRetry={runs.reload} hasData={runs.data !== undefined}>
        <DataTable columns={COLUMNS} rows={runs.data ?? []} rowKey={(r) => r.id} emptyMessage="Aún no hay reclasificaciones." />
        <Pager offset={offset} limit={rulesService.CLASSIFICATION_PAGE_SIZE} count={runs.data?.length ?? 0} onChange={setOffset} />
      </AsyncState>

      {showModal && (
        <ReclassifyModal
          onClose={() => setShowModal(false)}
          onCreated={() => {
            setOffset(0)
            runs.reload()
          }}
        />
      )}
    </>
  )
}
