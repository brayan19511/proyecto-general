import AsyncState from '../../../shared/components/AsyncState'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useApi } from '../../../shared/hooks/useApi'
import { formatDateTime } from '../../../shared/utils/format'
import * as gatewayService from '../services/gatewayService'

const ACTION: Record<string, { label: string; tone: 'success' | 'danger' }> = {
  'service_state.enable': { label: 'Habilitado', tone: 'success' },
  'service_state.disable': { label: 'Deshabilitado', tone: 'danger' },
  'ip_block.create': { label: 'Bloqueada', tone: 'danger' },
  'ip_block.delete': { label: 'Desbloqueada', tone: 'success' },
}

type GatewayHistoryProps = {
  resourceType: 'service_state' | 'ip_block'
  version: number // cambia tras cada acción para volver a pedirlo
  emails: Map<string, string>
}

// Últimos cambios de la central: qué, quién y cuándo (solo anexado).
export default function GatewayHistory({ resourceType, version, emails }: GatewayHistoryProps) {
  const events = useApi(() => gatewayService.listHistory(resourceType), [resourceType, version])

  return (
    <>
      <h2 className="h6 text-body-secondary mt-5 mb-2">Últimos cambios</h2>
      <AsyncState loading={events.loading} error={events.error} onRetry={events.reload} hasData={events.data !== undefined}>
        {(events.data ?? []).length === 0 ? (
          <p className="small text-body-secondary">Sin cambios registrados.</p>
        ) : (
          <ul className="list-group list-group-flush border rounded-3">
            {(events.data ?? []).map((e) => {
              const action = ACTION[e.action] ?? { label: e.action, tone: 'success' as const }
              const data = { ...e.before, ...e.after }
              const target = String(data.network ?? data.service ?? e.resource_id)
              const reason = data.reason ? String(data.reason) : null
              return (
                <li key={e.id} className="list-group-item d-flex flex-wrap align-items-center gap-2 small">
                  <span className="text-nowrap text-body-secondary">{formatDateTime(e.created_at)}</span>
                  <StatusBadge tone={action.tone} label={action.label} />
                  <span className="font-monospace">{target}</span>
                  {reason && <span className="text-body-secondary">— {reason}</span>}
                  <span className="ms-auto text-body-secondary">
                    {e.created_by ? emails.get(e.created_by) ?? e.created_by.slice(0, 8) : 'Sistema'}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </AsyncState>
    </>
  )
}
