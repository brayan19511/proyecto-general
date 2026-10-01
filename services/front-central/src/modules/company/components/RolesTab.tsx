import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import ConfirmDialog from '../../../shared/components/ConfirmDialog'
import DataTable, { type Column } from '../../../shared/components/DataTable'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import { SCOPE_LABEL, describePermission, withTexts } from '../permissionCatalog'
import * as orgService from '../services/orgService'
import type { Position, Role, RoleGrant } from '../types'
import CodeNameFormModal from './CodeNameFormModal'
import GrantModal from './GrantModal'
import RolePositionsModal from './RolePositionsModal'

type Pending =
  | { kind: 'delete'; role: Role }
  | { kind: 'restore'; role: Role }
  | { kind: 'unassign'; role: Role; position: Position }
  | { kind: 'revoke'; role: Role; grant: RoleGrant }

const PENDING_TEXT: Record<Pending['kind'], { title: string; label: string; done: string }> = {
  delete: { title: 'Dar de baja el rol', label: 'Dar de baja', done: 'Rol dado de baja' },
  restore: { title: 'Restaurar rol', label: 'Restaurar', done: 'Rol restaurado' },
  unassign: { title: 'Desasignar rol', label: 'Desasignar', done: 'Rol desasignado del puesto' },
  revoke: { title: 'Quitar permiso', label: 'Quitar', done: 'Permiso quitado del rol' },
}

function pendingMessage(p: Pending) {
  if (p.kind === 'restore') return `${p.role.name} vuelve a estar activo con sus permisos.`
  if (p.kind === 'revoke') {
    return `Quienes tengan un puesto con ${p.role.name} pierden ${describePermission(p.grant.permission).label} (${SCOPE_LABEL[p.grant.scope]}) desde su próxima solicitud, salvo que otro rol se lo dé.`
  }
  if (p.kind === 'unassign') return `Quienes tengan el puesto ${p.position.name} dejan de recibir los permisos de ${p.role.name}.`
  return `${p.role.name} deja de estar disponible. Solo se puede si ningún puesto lo tiene. Se puede restaurar.`
}

// Roles: buscar, crear, renombrar, dar de baja / restaurar, conceder permisos y
// asignarlos a puestos. El detalle de permisos se gestiona también en "Permisos".
export default function RolesTab() {
  const [includeDeleted, setIncludeDeleted] = useState(false)
  const [search, setSearch] = useState('')
  const roles = useApi(() => orgService.listRoles(includeDeleted), [includeDeleted])
  const catalog = useApi(() => orgService.listPermissionCatalog())
  const positions = useApi(() => orgService.listPositions())
  const activePositions = (positions.data ?? []).filter((p) => p.is_active)
  // Qué roles tiene cada puesto, para mostrar "en qué puestos está el rol".
  const roleMap = useApi(() => orgService.listPositionRolesMap(activePositions), [activePositions.map((p) => p.id).join(',')])
  const [form, setForm] = useState<{ role: Role | null } | null>(null)
  const [grantFor, setGrantFor] = useState<Role | null>(null)
  const [positionsFor, setPositionsFor] = useState<Role | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)

  const positionsOf = (role: Role) =>
    activePositions.filter((p) => roleMap.data?.get(p.id)?.some((r) => r.role_id === role.id))

  const term = search.trim().toLowerCase()
  const rows = [...(roles.data ?? [])]
    .sort((a, b) => a.name.localeCompare(b.name, 'es'))
    .filter((r) => !term || `${r.name} ${r.code} ${r.permissions.map((g) => g.permission).join(' ')}`.toLowerCase().includes(term))

  const confirm = async () => {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'delete') await orgService.deleteRole(pending.role.id)
      else if (pending.kind === 'restore') await orgService.restoreRole(pending.role.id)
      else if (pending.kind === 'revoke') await orgService.revokePermission(pending.role.id, pending.grant.id)
      else await orgService.removePositionRole(pending.position.id, pending.role.id)
      toast.success(PENDING_TEXT[pending.kind].done)
      roles.reload()
      roleMap.reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 asignado a puestos, o la empresa quedaría sin administradores
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const columns: Column<Role>[] = [
    {
      header: 'Rol',
      render: (r) => (
        <>
          <div>{r.name}</div>
          <div className="small text-body-secondary font-monospace">{r.code}</div>
        </>
      ),
    },
    {
      header: 'Permisos',
      render: (r) => (
        <div className="d-flex flex-wrap gap-1">
          {r.permissions.length === 0 && <span className="small text-body-secondary">Sin permisos</span>}
          {r.permissions.map((g) => (
            <span key={g.id} className="badge text-bg-light border fw-normal d-inline-flex align-items-center gap-1" title={g.permission}>
              {describePermission(g.permission).label} · {SCOPE_LABEL[g.scope]}
              {r.is_active && (
                <button type="button" className="btn btn-link p-0 lh-1 text-danger" title="Quitar este permiso del rol"
                  aria-label={`Quitar ${describePermission(g.permission).label} de ${r.name}`}
                  onClick={() => setPending({ kind: 'revoke', role: r, grant: g })}>
                  <i className="bi bi-x-lg" aria-hidden="true" />
                </button>
              )}
            </span>
          ))}
        </div>
      ),
    },
    {
      header: 'Puestos',
      render: (r) => {
        if (roleMap.loading && !roleMap.data) return <span className="spinner-border spinner-border-sm" aria-label="Cargando" />
        const list = positionsOf(r)
        return list.length === 0 ? (
          <span className="small text-body-secondary">Sin puestos</span>
        ) : (
          <div className="d-flex flex-wrap gap-1">
            {list.map((p) => (
              <span key={p.id} className="badge bg-primary-subtle text-primary-emphasis fw-normal d-inline-flex align-items-center gap-1">
                {p.name} · {p.area.name}
                {r.is_active && (
                  <button type="button" className="btn btn-link p-0 lh-1 text-primary-emphasis" title="Desasignar de este puesto"
                    aria-label={`Desasignar ${r.name} de ${p.name}`} onClick={() => setPending({ kind: 'unassign', role: r, position: p })}>
                    <i className="bi bi-x-lg" aria-hidden="true" />
                  </button>
                )}
              </span>
            ))}
          </div>
        )
      },
    },
    {
      header: 'Estado',
      render: (r) => <StatusBadge tone={r.is_active ? 'success' : 'secondary'} label={r.is_active ? 'Activo' : 'De baja'} />,
    },
    {
      header: 'Acciones',
      className: 'text-end text-nowrap',
      render: (r) =>
        r.is_active ? (
          <>
            <button type="button" className="btn btn-sm btn-outline-primary me-1" onClick={() => setGrantFor(r)} title="Conceder permiso"
              disabled={!catalog.data}>
              <i className="bi bi-key" aria-hidden="true" />
              <span className="visually-hidden">Conceder permiso a {r.name}</span>
            </button>
            <button type="button" className="btn btn-sm btn-outline-primary me-1" onClick={() => setPositionsFor(r)} title="Asignar o desasignar puestos"
              disabled={!roleMap.data}>
              <i className="bi bi-diagram-3" aria-hidden="true" />
              <span className="visually-hidden">Asignar o desasignar {r.name} de puestos</span>
            </button>
            <button type="button" className="btn btn-sm btn-outline-secondary me-1" onClick={() => setForm({ role: r })} title="Renombrar">
              <i className="bi bi-pencil" aria-hidden="true" />
              <span className="visually-hidden">Renombrar {r.name}</span>
            </button>
            <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => setPending({ kind: 'delete', role: r })} title="Dar de baja">
              <i className="bi bi-archive" aria-hidden="true" />
              <span className="visually-hidden">Dar de baja {r.name}</span>
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-sm btn-outline-success" onClick={() => setPending({ kind: 'restore', role: r })}>
            Restaurar
          </button>
        ),
    },
  ]

  return (
    <>
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">
        <input className="form-control form-control-sm" style={{ maxWidth: 280 }} placeholder="Buscar rol o permiso…"
          aria-label="Buscar roles" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="form-check form-switch mb-0">
          <input id="roles-deleted" type="checkbox" className="form-check-input" checked={includeDeleted}
            onChange={(e) => setIncludeDeleted(e.target.checked)} />
          <label htmlFor="roles-deleted" className="form-check-label">Ver dados de baja</label>
        </div>
        <button type="button" className="btn btn-primary ms-auto" onClick={() => setForm({ role: null })}>
          <i className="bi bi-plus-lg me-1" aria-hidden="true" />
          Nuevo rol
        </button>
      </div>

      <AsyncState loading={roles.loading} error={roles.error} onRetry={roles.reload} hasData={roles.data !== undefined}>
        <DataTable columns={columns} rows={rows} rowKey={(r) => r.id}
          emptyMessage={term ? 'Ningún rol coincide con la búsqueda.' : 'Aún no hay roles.'} />
      </AsyncState>

      {form && (
        <CodeNameFormModal
          title={form.role ? `Renombrar ${form.role.code}` : 'Nuevo rol'}
          existing={form.role}
          codePlaceholder="CONTADOR"
          namePlaceholder="Contador"
          save={(code, name) => (form.role ? orgService.renameRole(form.role.id, name) : orgService.createRole(code, name))}
          doneMessage={form.role ? 'Rol actualizado' : 'Rol creado. Concédele permisos y asígnalo a puestos.'}
          onClose={() => setForm(null)}
          onSaved={() => roles.reload()}
        />
      )}
      {grantFor && catalog.data && (
        <GrantModal action={{ kind: 'grant', roleId: grantFor.id }} roles={[grantFor]} catalog={withTexts(catalog.data)}
          onClose={() => setGrantFor(null)} onSaved={roles.reload} />
      )}
      {positionsFor && roleMap.data && (
        <RolePositionsModal role={positionsFor} positions={activePositions} rolesByPosition={roleMap.data}
          onClose={() => setPositionsFor(null)} onChanged={roleMap.reload} />
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pending ? PENDING_TEXT[pending.kind].title : ''}
        message={pending ? pendingMessage(pending) : ''}
        confirmLabel={pending ? PENDING_TEXT[pending.kind].label : ''}
        danger={pending?.kind !== 'restore'}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  )
}
