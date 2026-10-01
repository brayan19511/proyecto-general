import { useState } from 'react'
import { Navigate, useParams } from 'react-router'
import AsyncState from '../../../shared/components/AsyncState'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import RouteTabs from '../../../shared/components/RouteTabs'
import { useApi } from '../../../shared/hooks/useApi'
import LogDetailDialog from '../components/LogDetailDialog'
import LogFiltersBar from '../components/LogFiltersBar'
import LogsTable from '../components/LogsTable'
import TraceDialog from '../components/TraceDialog'
import { EMPTY_LOG_FILTERS } from '../logLabels'
import * as logsService from '../services/logsService'
import type { LogServiceKey } from '../services/logsService'

const TABS = logsService.LOG_SERVICES.map((s) => ({ label: s.label, to: `/monitoreo/logs/${s.key}` }))

// Un solo diálogo a la vez: el detalle de un log o la traza completa.
type Opened = { kind: 'log'; service: LogServiceKey; logId: string } | { kind: 'trace'; traceId: string } | null

// Solo platform admin (lo exigen los endpoints de logs de cada servicio).
export default function LogsPage() {
  const { service: serviceParam } = useParams()
  const service = logsService.findLogService(serviceParam)
  if (!service) return <Navigate to="/monitoreo/logs/gateway" replace />
  // key: cambiar de pestaña reinicia filtros y página.
  return <ServiceLogs key={service.key} service={service} />
}

function ServiceLogs({ service }: { service: (typeof logsService.LOG_SERVICES)[number] }) {
  const [filters, setFilters] = useState(EMPTY_LOG_FILTERS)
  const [offset, setOffset] = useState(0)
  const [opened, setOpened] = useState<Opened>(null)

  const logs = useApi(
    () => logsService.listLogs(service.key, filters, offset),
    [service.key, filters.outcome, filters.userId, filters.pathPrefix, filters.traceId, offset],
  )
  const users = useApi(logsService.listUsers)

  const emails = new Map((users.data ?? []).map((u) => [u.id, u.email]))
  const userEmail = (userId: string | null) => (userId ? emails.get(userId) ?? userId.slice(0, 8) : 'Anónimo')

  return (
    <>
      <PageHeader
        title="Actividad y logs"
        description="Cada solicitud por servicio: quién, desde qué IP, resultado, datos enviados (enmascarados) y pasos."
        actions={
          <button type="button" className="btn btn-outline-secondary" onClick={logs.reload}>
            <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
            Actualizar
          </button>
        }
      />
      <RouteTabs tabs={TABS} />

      <LogFiltersBar
        initial={filters}
        users={users.data ?? []}
        loginPath={service.loginPath}
        onApply={(f) => {
          setFilters(f)
          setOffset(0)
        }}
      />

      <AsyncState loading={logs.loading} error={logs.error} onRetry={logs.reload} hasData={logs.data !== undefined}>
        <LogsTable
          rows={logs.data ?? []}
          userEmail={userEmail}
          onOpen={(log) => setOpened({ kind: 'log', service: service.key, logId: log.id })}
          onTrace={(traceId) => setOpened({ kind: 'trace', traceId })}
        />
        <Pager offset={offset} limit={logsService.LOGS_PAGE_SIZE} count={logs.data?.length ?? 0} onChange={setOffset} />
      </AsyncState>

      {opened?.kind === 'log' && (
        <LogDetailDialog
          key={`${opened.service}-${opened.logId}`}
          service={opened.service}
          logId={opened.logId}
          userEmail={userEmail}
          onTrace={(traceId) => setOpened({ kind: 'trace', traceId })}
          onClose={() => setOpened(null)}
        />
      )}
      {opened?.kind === 'trace' && (
        <TraceDialog
          key={opened.traceId}
          traceId={opened.traceId}
          onOpenLog={(svc, logId) => setOpened({ kind: 'log', service: svc, logId })}
          onClose={() => setOpened(null)}
        />
      )}
    </>
  )
}
