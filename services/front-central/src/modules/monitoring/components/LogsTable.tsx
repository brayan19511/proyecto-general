import DataTable, { type Column } from '../../../shared/components/DataTable'
import { formatDateTime } from '../../../shared/utils/format'
import { formatDuration } from '../logLabels'
import type { LogEntry } from '../types'
import { HttpStatus, OutcomeBadge } from './LogBadges'

type LogsTableProps = {
  rows: LogEntry[]
  userEmail: (userId: string | null) => string
  onOpen: (log: LogEntry) => void
  onTrace: (traceId: string) => void
}

export default function LogsTable({ rows, userEmail, onOpen, onTrace }: LogsTableProps) {
  const columns: Column<LogEntry>[] = [
    { header: 'Fecha', className: 'text-nowrap', render: (l) => formatDateTime(l.started_at) },
    {
      header: 'Operación',
      render: (l) => (
        <button type="button" className="btn btn-link p-0 text-start text-decoration-none" onClick={() => onOpen(l)}>
          <span className="badge text-bg-light border me-2">{l.method}</span>
          <span className="font-monospace small">{l.path}</span>
        </button>
      ),
    },
    { header: 'HTTP', render: (l) => <HttpStatus code={l.status_code} /> },
    { header: 'Resultado', render: (l) => <OutcomeBadge outcome={l.outcome} /> },
    { header: 'Usuario', className: 'text-nowrap', render: (l) => userEmail(l.user_id) },
    { header: 'IP', className: 'text-nowrap font-monospace small', render: (l) => l.ip_address ?? '—' },
    { header: 'Duración', className: 'text-end text-nowrap', render: (l) => formatDuration(l.duration_ms) },
    {
      header: 'Traza',
      render: (l) => (
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          onClick={() => onTrace(l.trace_id)}
          title="Ver esta solicitud en todos los servicios"
          aria-label="Ver traza completa"
        >
          <i className="bi bi-diagram-2" aria-hidden="true" />
        </button>
      ),
    },
  ]

  return <DataTable columns={columns} rows={rows} rowKey={(l) => l.id} emptyMessage="No hay logs con estos filtros." />
}
