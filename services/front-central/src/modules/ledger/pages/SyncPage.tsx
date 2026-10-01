import { useState } from 'react'
import { LEDGER_ADMIN, useCanAccess } from '../../../shared/auth/access'
import AsyncState from '../../../shared/components/AsyncState'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import { useApi } from '../../../shared/hooks/useApi'
import { useInterval } from '../../../shared/hooks/useInterval'
import SyncRunModal from '../components/SyncRunModal'
import SyncRunsTable from '../components/SyncRunsTable'
import SyncStatusTable from '../components/SyncStatusTable'
import * as syncService from '../services/syncService'
import { RUN_STATUS } from '../syncLabels'
import type { SyncRunFilters, SyncRunStatus } from '../types'

const INITIAL_FILTERS: SyncRunFilters = { status: '', accountId: '', offset: 0 }

// Cada cuánto se refresca mientras hay ejecuciones pendientes o en curso.
const POLL_MS = 5000

// Ver: ledger.view o superior. Lanzar una sincronización manual: ledger.admin.
export default function SyncPage() {
  const canAccess = useCanAccess()
  const canSync = canAccess({ anyOf: LEDGER_ADMIN })
  const [showSyncModal, setShowSyncModal] = useState(false)
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const statusQuery = useApi(syncService.getSyncStatus)
  const runsQuery = useApi(() => syncService.listSyncRuns(filters), [filters.status, filters.accountId, filters.offset])

  const accounts = statusQuery.data ?? []
  const accountCode = (id: string) => accounts.find((a) => a.account_id === id)?.code ?? id.slice(0, 8)

  // Cambiar un filtro vuelve a la primera página.
  const setFilter = (change: Partial<SyncRunFilters>) => setFilters((f) => ({ ...f, offset: 0, ...change }))

  const { reload: reloadStatus } = statusQuery
  const { reload: reloadRuns } = runsQuery
  const reloadAll = () => {
    reloadStatus()
    reloadRuns()
  }

  // Mientras alguna ejecución visible esté abierta, se consulta su avance cada
  // POLL_MS. El fin de la solicitud HTTP no es el fin del trabajo: lo hace el worker.
  const hasOpenRuns = (runsQuery.data ?? []).some((r) => r.status === 'pending' || r.status === 'running')
  useInterval(hasOpenRuns, reloadAll, POLL_MS)

  return (
    <>
      <PageHeader
        title="Sincronización"
        description="Estado de la carga desde SAP por cuenta y ejecuciones recientes."
        actions={
          <>
            <button type="button" className="btn btn-outline-secondary" onClick={reloadAll}>
              <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
              Actualizar
            </button>
            {canSync && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setShowSyncModal(true)}
                disabled={accounts.length === 0}
                title={accounts.length === 0 ? 'La empresa no tiene cuentas registradas' : undefined}
              >
                <i className="bi bi-cloud-download me-1" aria-hidden="true" />
                Sincronizar
              </button>
            )}
          </>
        }
      />

      {hasOpenRuns && (
        <div className="alert alert-info d-flex align-items-center gap-2 py-2" role="status">
          <span className="spinner-border spinner-border-sm" aria-hidden="true" />
          Hay sincronizaciones en proceso. El avance se actualiza solo.
        </div>
      )}

      <h2 className="h6 text-body-secondary mb-2">Estado por cuenta</h2>
      <AsyncState
        loading={statusQuery.loading}
        error={statusQuery.error}
        onRetry={statusQuery.reload}
        hasData={statusQuery.data !== undefined}
      >
        <SyncStatusTable rows={accounts} />
      </AsyncState>

      <div className="d-flex flex-wrap align-items-end justify-content-between gap-2 mt-5 mb-2">
        <h2 className="h6 text-body-secondary mb-0">Ejecuciones</h2>
        <div className="d-flex flex-wrap gap-2">
          <select
            className="form-select form-select-sm w-auto"
            aria-label="Filtrar por estado"
            value={filters.status}
            onChange={(e) => setFilter({ status: e.target.value as SyncRunStatus | '' })}
          >
            <option value="">Todos los estados</option>
            {Object.entries(RUN_STATUS).map(([value, { label }]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <select
            className="form-select form-select-sm w-auto"
            aria-label="Filtrar por cuenta"
            value={filters.accountId}
            onChange={(e) => setFilter({ accountId: e.target.value })}
          >
            <option value="">Todas las cuentas</option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>{a.code}</option>
            ))}
          </select>
        </div>
      </div>

      <AsyncState
        loading={runsQuery.loading}
        error={runsQuery.error}
        onRetry={runsQuery.reload}
        hasData={runsQuery.data !== undefined}
      >
        <SyncRunsTable rows={runsQuery.data ?? []} accountCode={accountCode} />
        <Pager
          offset={filters.offset}
          limit={syncService.SYNC_RUNS_PAGE_SIZE}
          count={runsQuery.data?.length ?? 0}
          onChange={(offset) => setFilters((f) => ({ ...f, offset }))}
        />
      </AsyncState>

      {showSyncModal && (
        <SyncRunModal
          accounts={accounts}
          onClose={() => setShowSyncModal(false)}
          onCreated={() => {
            // La nueva ejecución aparece arriba: se vuelve a la primera página sin filtros.
            setFilters(INITIAL_FILTERS)
            reloadAll()
          }}
        />
      )}
    </>
  )
}
