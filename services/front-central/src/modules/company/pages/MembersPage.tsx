import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import PageHeader from '../../../shared/components/PageHeader'
import Pager from '../../../shared/components/Pager'
import StatusBadge from '../../../shared/components/StatusBadge'
import { useSessionStore } from '../../../shared/auth/sessionStore'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { formatDate } from '../../../shared/utils/format'
import AddMemberModal from '../components/AddMemberModal'
import AssignPositionModal from '../components/AssignPositionModal'
import * as membersService from '../services/membersService'
import * as orgService from '../services/orgService'
import type { Member } from '../types'

// Acción que pide confirmación antes de enviarse.
type Pending =
  | { kind: 'suspend' | 'reactivate' | 'remove'; member: Member }
  | { kind: 'unassign'; member: Member; position: Member['positions'][number] }

const fullName = (m: Member) => [m.first_names, m.last_names].filter(Boolean).join(' ')

const CONFIRM: Record<Pending['kind'], { title: string; label: string; done: string; danger: boolean; message: (p: Pending) => string }> = {
  suspend: {
    title: 'Suspender miembro', label: 'Suspender', done: 'Miembro suspendido', danger: true,
    message: (p) => `${p.member.email} pierde el acceso a esta empresa de inmediato, pero conserva sus puestos: al reactivarlo vuelve tal como estaba.`,
  },
  reactivate: {
    title: 'Reactivar miembro', label: 'Reactivar', done: 'Miembro reactivado', danger: false,
    message: (p) => `${p.member.email} recupera el acceso con los puestos que tenía.`,
  },
  remove: {
    title: 'Dar de baja de la empresa', label: 'Dar de baja', done: 'Miembro dado de baja', danger: true,
    message: (p) => `${p.member.email} deja la empresa y se le retiran todos sus puestos. Su cuenta no se borra y queda el historial. Para una ausencia temporal usa "Suspender".`,
  },
  unassign: {
    title: 'Desasignar puesto', label: 'Desasignar', done: 'Puesto desasignado', danger: true,
    message: (p) => (p.kind === 'unassign' ? `${p.member.email} deja de tener el puesto ${p.position.name} y los roles que heredaba de él.` : ''),
  },
}

// Empresa › Miembros (fase 1: solo platform admin). Sobre la empresa activa.
export default function MembersPage() {
  const companyName = useSessionStore((s) => s.companies.find((c) => c.id === s.companyId)?.name ?? '')
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const members = useApi(() => membersService.listMembers(offset), [offset])
  const positions = useApi(() => orgService.listPositions())
  const [adding, setAdding] = useState(false)
  const [assigningTo, setAssigningTo] = useState<Member | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)

  const term = search.trim().toLowerCase()
  const rows = (members.data ?? []).filter(
    (m) => !term || `${m.email} ${fullName(m)} ${m.positions.map((p) => `${p.name} ${p.area.name}`).join(' ')}`.toLowerCase().includes(term),
  )

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'suspend') await membersService.setMemberActive(pending.member.id, false)
      else if (pending.kind === 'reactivate') await membersService.setMemberActive(pending.member.id, true)
      else if (pending.kind === 'remove') await membersService.removeMember(pending.member.id)
      else if (pending.kind === 'unassign') await membersService.unassignPosition(pending.member.id, pending.position.id)
      toast.success(CONFIRM[pending.kind].done)
      members.reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 la empresa quedaría sin administradores, 403…
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const columns: Column<Member>[] = [
    {
      header: 'Miembro',
      render: (m) => (
        <>
          <div>{fullName(m) || m.email}</div>
          {fullName(m) && <div className="small text-body-secondary">{m.email}</div>}
        </>
      ),
    },
    {
      header: 'Puestos',
      render: (m) => (
        <div className="d-flex flex-wrap gap-1 align-items-center">
          {m.positions.length === 0 && <span className="small text-body-secondary">Sin puesto (sin permisos)</span>}
          {m.positions.map((p) => (
            <span key={p.id} className="badge bg-primary-subtle text-primary-emphasis fw-normal d-inline-flex align-items-center gap-1">
              {p.name} · {p.area.name}
              <button type="button" className="btn btn-link p-0 lh-1 text-primary-emphasis" title="Desasignar este puesto"
                aria-label={`Desasignar puesto ${p.name}`} onClick={() => setPending({ kind: 'unassign', member: m, position: p })}>
                <i className="bi bi-x-lg" aria-hidden="true" />
              </button>
            </span>
          ))}
          <button type="button" className="btn btn-sm btn-link p-0" onClick={() => setAssigningTo(m)}>
            <i className="bi bi-plus-lg" aria-hidden="true" /> Puesto
          </button>
        </div>
      ),
    },
    {
      header: 'Estado',
      render: (m) => <StatusBadge tone={m.is_active ? 'success' : 'warning'} label={m.is_active ? 'Activo' : 'Suspendido'} />,
    },
    { header: 'Desde', className: 'text-nowrap', render: (m) => formatDate(m.created_at.slice(0, 10)) },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (m) => (
        <>
          <button type="button" className="btn btn-sm btn-outline-secondary me-1"
            onClick={() => setPending({ kind: m.is_active ? 'suspend' : 'reactivate', member: m })}>
            {m.is_active ? 'Suspender' : 'Reactivar'}
          </button>
          <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'remove', member: m })}
            aria-label={`Dar de baja a ${m.email}`} title="Dar de baja de la empresa">
            <i className="bi bi-person-dash" aria-hidden="true" />
          </button>
        </>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Miembros"
        description={`Personas con acceso a ${companyName}. Los permisos se heredan de sus puestos.`}
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
            <i className="bi bi-person-plus me-1" aria-hidden="true" />
            Agregar miembro
          </button>
        }
      />

      <input className="form-control form-control-sm mb-3" style={{ maxWidth: 320 }} placeholder="Buscar por nombre, correo o puesto…"
        aria-label="Buscar miembros" value={search} onChange={(e) => setSearch(e.target.value)} />

      <AsyncState loading={members.loading} error={members.error} onRetry={members.reload} hasData={members.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(m) => m.id}
          emptyMessage={term ? 'Nadie coincide con la búsqueda.' : 'Aún no hay miembros.'} />
        <Pager offset={offset} limit={membersService.MEMBERS_PAGE_SIZE} count={members.data?.length ?? 0} onChange={setOffset} />
      </AsyncState>

      {adding && <AddMemberModal onClose={() => setAdding(false)} onAdded={members.reload} />}
      {assigningTo && (
        <AssignPositionModal
          member={assigningTo}
          positions={(positions.data ?? []).filter((p) => p.is_active)}
          onClose={() => setAssigningTo(null)}
          onAssigned={members.reload}
        />
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pending ? CONFIRM[pending.kind].title : ''}
        message={pending ? CONFIRM[pending.kind].message(pending) : ''}
        confirmLabel={pending ? CONFIRM[pending.kind].label : ''}
        danger={pending ? CONFIRM[pending.kind].danger : false}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
