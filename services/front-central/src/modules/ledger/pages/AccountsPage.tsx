import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDate } from '../../../shared/utils/format'
import AccountFormModal from '../components/AccountFormModal'
import * as accountsService from '../services/accountsService'
import type { Account } from '../types'

// Contabilidad › Cuentas (solo ledger.admin): qué cuentas de SAP sincroniza
// libro-mayor para esta empresa.
export default function AccountsPage() {
  const [includeInactive, setIncludeInactive] = useState(false)
  const [search, setSearch] = useState('')
  const accounts = useApi(() => accountsService.listAccounts(includeInactive), [includeInactive])
  const [form, setForm] = useState<{ account: Account | null } | null>(null)
  const [toDeactivate, setToDeactivate] = useState<Account | null>(null)
  const [busy, setBusy] = useState(false)

  const term = search.trim().toLowerCase()
  const rows = (accounts.data ?? []).filter((a) => !term || `${a.code} ${a.name ?? ''}`.toLowerCase().includes(term))

  const deactivate = async () => {
    if (!toDeactivate) return
    setBusy(true)
    try {
      await accountsService.deactivateAccount(toDeactivate.id)
      toast.success('Cuenta dada de baja')
      accounts.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setToDeactivate(null)
    }
  }

  const columns: Column<Account>[] = [
    { header: 'Código', render: (a) => <span className="font-monospace">{a.code}{a.match_mode === 'prefix' ? '*' : ''}</span> },
    { header: 'Coincidencia', render: (a) => (a.match_mode === 'prefix' ? 'Empieza con' : 'Cuenta exacta') },
    { header: 'Nombre', render: (a) => a.name ?? <span className="text-body-secondary">—</span> },
    { header: 'Registrada', className: 'text-nowrap', render: (a) => formatDate(a.created_at.slice(0, 10)) },
    {
      header: 'Estado',
      render: (a) => <StatusBadge tone={a.is_active ? 'success' : 'secondary'} label={a.is_active ? 'Se sincroniza' : 'De baja'} />,
    },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (a) =>
        a.is_active && (
          <>
            <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setForm({ account: a })}
              aria-label={`Editar cuenta ${a.code}`} title="Editar">
              <i className="bi bi-pencil" aria-hidden="true" />
            </button>
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setToDeactivate(a)}
              aria-label={`Dar de baja la cuenta ${a.code}`} title="Dar de baja">
              <i className="bi bi-archive" aria-hidden="true" />
            </button>
          </>
        ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Cuentas"
        description="Cuentas de SAP que se sincronizan para esta empresa. Por prefijo incluye todas las que empiezan así."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setForm({ account: null })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva cuenta
          </button>
        }
      />

      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 280 }} placeholder="Buscar código o nombre…"
          aria-label="Buscar cuentas" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="form-check form-switch mb-0">
          <input id="acc-inactive" type="checkbox" className="form-check-input" checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)} />
          <label htmlFor="acc-inactive" className="form-check-label">Ver dadas de baja</label>
        </div>
      </div>

      <AsyncState loading={accounts.loading} error={accounts.error} onRetry={accounts.reload} hasData={accounts.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(a) => a.id}
          emptyMessage={term ? 'Ninguna cuenta coincide.' : 'Aún no hay cuentas registradas.'} />
      </AsyncState>

      {form && <AccountFormModal account={form.account} onClose={() => setForm(null)} onSaved={accounts.reload} />}

      <ConfirmDialog
        open={toDeactivate !== null}
        title="Dar de baja la cuenta"
        message={`La cuenta ${toDeactivate?.code ?? ''} deja de sincronizarse. Las líneas ya traídas, su historial y la fila se conservan. Para volver a sincronizarla, registra otra.`}
        confirmLabel="Dar de baja"
        danger
        busy={busy}
        onConfirm={deactivate}
        onCancel={() => setToDeactivate(null)}
      />
    </>
  )
}
