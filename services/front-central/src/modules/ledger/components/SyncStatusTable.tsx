import DataTable, { type Column } from '../../../shared/components/DataTable'
import StatusBadge from '../../../shared/components/StatusBadge'
import { formatDate, formatDateTime } from '../../../shared/utils/format'
import { RUN_KIND, RUN_STATUS } from '../syncLabels'
import type { SyncStatus } from '../types'

const COLUMNS: Column<SyncStatus>[] = [
  {
    header: 'Cuenta',
    render: (s) => (
      <>
        <div className="fw-semibold">{s.code}</div>
        {s.name && <div className="small text-body-secondary">{s.name}</div>}
      </>
    ),
  },
  {
    header: 'Estado',
    render: (s) =>
      s.consecutive_failures > 0 ? (
        <StatusBadge tone="danger" label={`${s.consecutive_failures} fallos seguidos`} />
      ) : s.last_success_at ? (
        <StatusBadge tone="success" label="Al día" />
      ) : (
        <StatusBadge tone="secondary" label="Sin carga inicial" />
      ),
  },
  {
    header: 'Última correcta',
    className: 'text-nowrap',
    render: (s) =>
      s.last_success_at ? (
        <>
          <div>{formatDateTime(s.last_success_at)}</div>
          <div className="small text-body-secondary">hace {s.hours_since_success} h</div>
        </>
      ) : (
        '—'
      ),
  },
  {
    header: 'Próximo delta desde',
    className: 'text-nowrap',
    render: (s) => (s.watermark ? formatDate(s.watermark) : '—'),
  },
  {
    header: 'Última ejecución',
    render: (s) =>
      s.last_run_status ? (
        <>
          <StatusBadge {...RUN_STATUS[s.last_run_status]} />
          {s.last_run_kind && (
            <span className="small text-body-secondary ms-2">
              {RUN_KIND[s.last_run_kind as keyof typeof RUN_KIND] ?? s.last_run_kind}
            </span>
          )}
        </>
      ) : (
        '—'
      ),
  },
  {
    header: 'Último error',
    render: (s) => (s.last_error ? <span className="small text-danger-emphasis">{s.last_error}</span> : '—'),
  },
]

export default function SyncStatusTable({ rows }: { rows: SyncStatus[] }) {
  return (
    <DataTable
      columns={COLUMNS}
      rows={rows}
      rowKey={(s) => s.account_id}
      emptyMessage="La empresa no tiene cuentas registradas para sincronizar."
    />
  )
}
