import { useState, type FormEvent } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDate } from '../../../shared/utils/format'
import ResetPasswordModal from '../components/ResetPasswordModal'
import UserDetailModal from '../components/UserDetailModal'
import * as usersService from '../services/usersService'
import type { AdminUser } from '../types'

// Plataforma › Usuarios (solo platform admin): todas las cuentas, de cualquier
// empresa. El alta en una empresa se hace en Empresa › Miembros.
export default function UsersPage() {
  const [query, setQuery] = useState('')
  const [email, setEmail] = useState('')
  const [offset, setOffset] = useState(0)
  const users = useApi(() => usersService.searchUsers(email, offset), [email, offset])
  const [detailOf, setDetailOf] = useState<string | null>(null)
  const [resetFor, setResetFor] = useState<AdminUser | null>(null)
  const [revokeFor, setRevokeFor] = useState<AdminUser | null>(null)
  const [busy, setBusy] = useState(false)

  const search = (event: FormEvent) => {
    event.preventDefault()
    setEmail(query)
    setOffset(0)
  }

  const revoke = async () => {
    if (!revokeFor) return
    setBusy(true)
    try {
      const { revoked } = await usersService.revokeSessions(revokeFor.id)
      toast.success(`Se cerraron ${revoked} ${revoked === 1 ? 'sesión' : 'sesiones'}`)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
      setRevokeFor(null)
    }
  }

  const columns: Column<AdminUser>[] = [
    {
      header: 'Correo',
      render: (u) => (
        <button type="button" className="btn btn-link p-0 text-start" onClick={() => setDetailOf(u.id)}>{u.email}</button>
      ),
    },
    {
      header: 'Tipo',
      render: (u) => (u.is_platform_admin ? <StatusBadge tone="info" label="Admin de plataforma" /> : <span className="small text-body-secondary">Usuario</span>),
    },
    { header: 'Registrado', className: 'text-nowrap', render: (u) => formatDate(u.created_at.slice(0, 10)) },
    {
      header: 'Estado',
      render: (u) => <StatusBadge tone={u.is_active ? 'success' : 'secondary'} label={u.is_active ? 'Activa' : 'Inhabilitada'} />,
    },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (u) => (
        <>
          <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setDetailOf(u.id)}>Ver</button>
          <button type="button" className="btn btn-sm btn-outline-primary me-1" onClick={() => setResetFor(u)}>
            <i className="bi bi-key me-1" aria-hidden="true" />
            Contraseña
          </button>
          <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setRevokeFor(u)}
            aria-label={`Cerrar sesiones de ${u.email}`} title="Cerrar todas sus sesiones">
            <i className="bi bi-box-arrow-right" aria-hidden="true" />
          </button>
        </>
      ),
    },
  ]

  return (
    <>
      <PageHeader title="Usuarios" description="Todas las cuentas de la plataforma. Para darles acceso a una empresa, usa Empresa › Miembros." />

      <form className="d-flex gap-2 mb-3" style={{ maxWidth: 420 }} onSubmit={search}>
        <input className="form-control form-control-sm" placeholder="Buscar por correo (parte del correo)…" aria-label="Buscar usuarios"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        <button type="submit" className="btn btn-sm btn-primary">Buscar</button>
      </form>

      <AsyncState loading={users.loading} error={users.error} onRetry={users.reload} hasData={users.data !== undefined}>
        <DataTable columns={columns} rows={users.data ?? []} rowKey={(u) => u.id}
          emptyMessage={email ? 'Ningún correo coincide.' : 'Aún no hay usuarios.'} />
        <Pager offset={offset} limit={usersService.USERS_PAGE_SIZE} count={users.data?.length ?? 0} onChange={setOffset} />
      </AsyncState>

      {detailOf && <UserDetailModal userId={detailOf} onClose={() => setDetailOf(null)} />}
      {resetFor && <ResetPasswordModal user={resetFor} onClose={() => setResetFor(null)} />}

      <ConfirmDialog
        open={revokeFor !== null}
        title="Cerrar todas sus sesiones"
        message={`${revokeFor?.email ?? ''} tendrá que volver a iniciar sesión en todos sus dispositivos. Su contraseña no cambia.`}
        confirmLabel="Cerrar sesiones"
        danger
        busy={busy}
        onConfirm={revoke}
        onCancel={() => setRevokeFor(null)}
      />
    </>
  )
}
