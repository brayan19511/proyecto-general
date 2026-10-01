import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import SmtpAccountFormModal from '../components/SmtpAccountFormModal'
import { SECURITY_LABEL, SMTP_TEST_ERROR } from '../labels'
import * as notificationsService from '../services/notificationsService'
import type { SmtpAccount } from '../types'

// Plataforma › Cuentas SMTP (solo platform admin en el front): desde dónde se envía, en orden
// de prioridad. La contraseña se guarda cifrada y nunca se muestra.
export default function SmtpAccountsPage() {
  const [includeInactive, setIncludeInactive] = useState(false)
  const accounts = useApi(() => notificationsService.listSmtpAccounts(includeInactive), [includeInactive])
  const [form, setForm] = useState<{ account: SmtpAccount | null } | null>(null)
  const [pending, setPending] = useState<{ kind: 'delete' | 'restore'; account: SmtpAccount } | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const test = async (a: SmtpAccount) => {
    setTesting(a.id)
    try {
      const result = await notificationsService.testSmtpAccount(a.id)
      if (result.ok) toast.success(`${a.name}: conexión y autenticación correctas`)
      else toast.error(`${a.name}: ${SMTP_TEST_ERROR[result.error_kind ?? 'unknown'] ?? result.error_kind}`)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setTesting(null)
    }
  }

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'delete') await notificationsService.deleteSmtpAccount(pending.account.id)
      else await notificationsService.restoreSmtpAccount(pending.account.id)
      toast.success(pending.kind === 'delete' ? 'Cuenta dada de baja' : 'Cuenta restaurada')
      accounts.reload()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const columns: Column<SmtpAccount>[] = [
    { header: 'Prioridad', className: 'text-body-secondary', render: (a) => a.priority },
    {
      header: 'Cuenta',
      render: (a) => (
        <>
          <div>{a.name}</div>
          <div className="small text-body-secondary">{a.from_name ? `${a.from_name} <${a.from_email}>` : a.from_email}</div>
        </>
      ),
    },
    {
      header: 'Servidor',
      className: 'small',
      render: (a) => (
        <>
          <span className="font-monospace">{a.host}:{a.port}</span> · {SECURITY_LABEL[a.security]}
          <div className="text-body-secondary">{a.username ?? 'Sin usuario'}{a.has_password ? ' · con contraseña' : ''}</div>
        </>
      ),
    },
    { header: 'Estado', render: (a) => <StatusBadge tone={a.is_active ? 'success' : 'secondary'} label={a.is_active ? 'Activa' : 'De baja'} /> },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (a) =>
        a.is_active ? (
          <>
            <button type="button" className="btn btn-sm btn-outline-primary me-1" disabled={testing !== null} onClick={() => test(a)}>
              {testing === a.id ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : 'Probar'}
            </button>
            <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setForm({ account: a })} title="Editar">
              <i className="bi bi-pencil" aria-hidden="true" />
              <span className="visually-hidden">Editar {a.name}</span>
            </button>
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'delete', account: a })} title="Dar de baja">
              <i className="bi bi-archive" aria-hidden="true" />
              <span className="visually-hidden">Dar de baja {a.name}</span>
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-sm btn-outline-success" onClick={() => setPending({ kind: 'restore', account: a })}>Restaurar</button>
        ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Cuentas SMTP"
        description="Cuentas de la empresa activa, para todos los módulos. Se usa la de menor prioridad; si falla, la siguiente. Probar revisa conexión y usuario sin enviar correo."
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setForm({ account: null })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            Nueva cuenta
          </button>
        }
      />
      <div className="form-check form-switch mb-3">
        <input id="smtp-inactive" type="checkbox" className="form-check-input" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
        <label htmlFor="smtp-inactive" className="form-check-label">Ver dadas de baja</label>
      </div>
      <AsyncState loading={accounts.loading} error={accounts.error} onRetry={accounts.reload} hasData={accounts.data !== undefined}>
        <DataTable columns={columns} rows={accounts.data?.items ?? []} rowKey={(a) => a.id}
          emptyMessage="Aún no hay cuentas: sin una activa no se pueden crear envíos." />
      </AsyncState>

      {form && <SmtpAccountFormModal account={form.account} onClose={() => setForm(null)} onSaved={accounts.reload} />}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'delete' ? 'Dar de baja la cuenta' : 'Restaurar cuenta'}
        message={pending?.kind === 'delete'
          ? `${pending.account.name} deja de usarse para enviar. Se puede restaurar.`
          : `${pending?.account.name ?? ''} vuelve a usarse según su prioridad.`}
        confirmLabel={pending?.kind === 'delete' ? 'Dar de baja' : 'Restaurar'}
        danger={pending?.kind === 'delete'}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
