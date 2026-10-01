import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { PAYMENTS_MANAGE, useCanAccess } from '../../../shared/auth/access'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import ProviderFormModal from '../components/ProviderFormModal'
import * as paymentsService from '../services/paymentsService'
import type { Provider } from '../types'

// Tesorería › Proveedores: maestro con que se agrupan las constancias. Ver: cualquier
// permiso de pagos; editar: payments.providers.manage o admin.
export default function ProvidersPage() {
  const can = useCanAccess()
  const canManage = can({ anyOf: PAYMENTS_MANAGE })
  const [search, setSearch] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [offset, setOffset] = useState(0)
  const term = search.trim()
  const providers = useApi(() => paymentsService.listProviders(term, includeInactive, offset), [term, includeInactive, offset])
  const [form, setForm] = useState<{ provider: Provider | null } | null>(null)
  const [pending, setPending] = useState<{ kind: 'delete' | 'restore'; provider: Provider } | null>(null)
  const [busy, setBusy] = useState(false)

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'delete') await paymentsService.deleteProvider(pending.provider.id)
      else await paymentsService.restoreProvider(pending.provider.id)
      toast.success(pending.kind === 'delete' ? 'Proveedor dado de baja' : 'Proveedor restaurado')
      providers.reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 al restaurar si choca con otro activo
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const columns: Column<Provider>[] = [
    { header: 'RUC / DNI', className: 'font-monospace text-nowrap', render: (p) => p.tax_id },
    {
      header: 'Proveedor',
      render: (p) => (
        <>
          <div>{p.legal_name}</div>
          {p.commercial_names.length > 0 && <div className="small text-body-secondary">{p.commercial_names.join(' · ')}</div>}
        </>
      ),
    },
    {
      header: 'Correos de pago',
      className: 'small',
      render: (p) => (p.payment_emails.length ? p.payment_emails.join(', ') : <span className="text-warning-emphasis">Sin correo</span>),
    },
    { header: 'Estado', render: (p) => <StatusBadge tone={p.is_active ? 'success' : 'secondary'} label={p.is_active ? 'Activo' : 'De baja'} /> },
    ...(canManage
      ? [{
          header: 'Acciones',
          className: 'text-end text-nowrap',
          render: (p: Provider) =>
            p.is_active ? (
              <>
                <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setForm({ provider: p })} title="Editar">
                  <i className="bi bi-pencil" aria-hidden="true" />
                  <span className="visually-hidden">Editar {p.legal_name}</span>
                </button>
                <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'delete', provider: p })} title="Dar de baja">
                  <i className="bi bi-archive" aria-hidden="true" />
                  <span className="visually-hidden">Dar de baja {p.legal_name}</span>
                </button>
              </>
            ) : (
              <button type="button" className="btn btn-sm btn-outline-success" onClick={() => setPending({ kind: 'restore', provider: p })}>Restaurar</button>
            ),
        }]
      : []),
  ]

  return (
    <>
      <PageHeader
        title="Proveedores"
        description="Con su RUC/DNI y nombres se reconocen en las constancias; a sus correos se envían los avisos de pago."
        actions={
          canManage && (
            <button type="button" className="btn btn-primary" onClick={() => setForm({ provider: null })}>
              <i className="bi bi-plus-lg me-1" aria-hidden="true" />
              Nuevo proveedor
            </button>
          )
        }
      />
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 300 }} placeholder="Buscar por RUC, DNI o razón social…"
          aria-label="Buscar proveedores" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0) }} />
        <div className="form-check form-switch mb-0">
          <input id="prov-inactive" type="checkbox" className="form-check-input" checked={includeInactive}
            onChange={(e) => { setIncludeInactive(e.target.checked); setOffset(0) }} />
          <label htmlFor="prov-inactive" className="form-check-label">Ver dados de baja</label>
        </div>
      </div>
      <AsyncState loading={providers.loading} error={providers.error} onRetry={providers.reload} hasData={providers.data !== undefined}>
        <DataTable columns={columns} rows={providers.data?.items ?? []} rowKey={(p) => p.id}
          emptyMessage={term ? 'Ningún proveedor coincide.' : 'Aún no hay proveedores.'} />
        <Pager offset={offset} limit={paymentsService.PAGE_SIZE} count={providers.data?.items.length ?? 0}
          total={providers.data?.total} onChange={setOffset} />
      </AsyncState>

      {form && <ProviderFormModal provider={form.provider} onClose={() => setForm(null)} onSaved={providers.reload} />}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'delete' ? 'Dar de baja el proveedor' : 'Restaurar proveedor'}
        message={pending?.kind === 'delete'
          ? `${pending.provider.legal_name} deja de reconocerse en los lotes nuevos y en los borradores. Se puede restaurar.`
          : `${pending?.provider.legal_name ?? ''} vuelve a reconocerse en las constancias.`}
        confirmLabel={pending?.kind === 'delete' ? 'Dar de baja' : 'Restaurar'}
        danger={pending?.kind === 'delete'}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
