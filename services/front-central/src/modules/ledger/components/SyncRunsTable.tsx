import DataTable, { type Column } from '../../../shared/components/DataTable'
import StatusBadge from '../../../shared/components/StatusBadge'
import { formatDate, formatDateTime } from '../../../shared/utils/format'
import { RUN_KIND, RUN_STATUS } from '../syncLabels'
import type { SyncRun } from '../types'

const numberFormat = new Intl.NumberFormat('es-PE')

type SyncRunsTableProps = {
  rows: SyncRun[]
  accountCode: (accountId: string) => string
}

export default function SyncRunsTable({ rows, accountCode }: SyncRunsTableProps) {
  const columns: Column<SyncRun>[] = [
    { header: 'Creada', className: 'text-nowrap', render: (r) => formatDateTime(r.created_at) },
    { header: 'Cuenta', render: (r) => accountCode(r.account_id) },
    {
      header: 'Tipo',
      render: (r) => (
        <>
          <div>{RUN_KIND[r.kind]}</div>
          <div className="small text-body-secondary">{r.origin === 'schedule' ? 'Horario' : 'Usuario'}</div>
        </>
      ),
    },
    { header: 'Estado', render: (r) => <StatusBadge {...RUN_STATUS[r.status]} /> },
    {
      header: 'Rango',
      className: 'text-nowrap',
      render: (r) => `${formatDate(r.date_from)} – ${formatDate(r.date_to)}`,
    },
    {
      header: 'Avance',
      render: (r) => {
        const percent = r.days_total > 0 ? Math.round((r.days_done / r.days_total) * 100) : 0
        return (
          <div style={{ minWidth: 110 }}>
            <div className="progress" style={{ height: 6 }} role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
              <div className={`progress-bar ${r.status === 'failed' ? 'bg-danger' : ''}`} style={{ width: `${percent}%` }} />
            </div>
            <div className="small text-body-secondary mt-1">{r.days_done} de {r.days_total} días</div>
          </div>
        )
      },
    },
    {
      header: 'Filas',
      className: 'text-nowrap',
      render: (r) => (
        <div className="small">
          <div>Leídas: {numberFormat.format(r.rows_read)}</div>
          <div className="text-body-secondary">
            Nuevas {numberFormat.format(r.rows_inserted)} · Act. {numberFormat.format(r.rows_updated)}
          </div>
        </div>
      ),
    },
    {
      header: 'Fin',
      className: 'text-nowrap',
      render: (r) => (r.finished_at ? formatDateTime(r.finished_at) : '—'),
    },
    {
      header: 'Error',
      render: (r) => (r.safe_error ? <span className="small text-danger-emphasis">{r.safe_error}</span> : '—'),
    },
  ]

  return (
    <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} emptyMessage="No hay ejecuciones con estos filtros." />
  )
}
