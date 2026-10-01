import { useState } from 'react'
import AsyncState from '../../../shared/components/AsyncState'
import Dialog from '../../../shared/components/Dialog'
import StatusBadge from '../../../shared/components/StatusBadge'
import { errorMessage, useApi } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as orgService from '../services/orgService'
import type { Position, Role } from '../types'

type PositionRolesModalProps = {
  position: Position
  roles: Role[] // activos de la empresa
  onClose: () => void
}

// Roles del puesto: quien tenga el puesto hereda sus permisos en esta empresa.
export default function PositionRolesModal({ position, roles, onClose }: PositionRolesModalProps) {
  const linked = useApi(() => orgService.listPositionRoles(position.id), [position.id])
  const [roleId, setRoleId] = useState('')
  const [busy, setBusy] = useState(false)

  const linkedIds = new Set((linked.data ?? []).map((r) => r.role_id))
  const available = roles.filter((r) => !linkedIds.has(r.id))

  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try {
      await action()
      toast.success(done)
      setRoleId('')
      linked.reload()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 la empresa quedaría sin administradores, 403 delegación
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onClose={onClose} busy={busy} labelledBy="pos-roles-title">
      <div className="card-header bg-transparent d-flex align-items-center">
        <div className="me-auto">
          <h2 id="pos-roles-title" className="h5 mb-0">Roles de {position.name}</h2>
          <div className="small text-body-secondary">{position.area.name} · {position.code}</div>
        </div>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} disabled={busy} />
      </div>
      <div className="card-body">
        <AsyncState loading={linked.loading} error={linked.error} onRetry={linked.reload} hasData={linked.data !== undefined}>
          {(linked.data ?? []).length === 0 ? (
            <p className="text-body-secondary">Sin roles: quien tenga este puesto no recibe permisos.</p>
          ) : (
            <ul className="list-group mb-3">
              {(linked.data ?? []).map((r) => (
                <li key={r.role_id} className="list-group-item d-flex align-items-center justify-content-between gap-2">
                  <span>
                    {r.name} <span className="small text-body-secondary font-monospace">{r.code}</span>
                    {!r.is_active && <span className="ms-2"><StatusBadge tone="warning" label="Suspendido" /></span>}
                  </span>
                  <button type="button" className="btn btn-sm btn-outline-danger" disabled={busy}
                    onClick={() => run(() => orgService.removePositionRole(position.id, r.role_id), 'Rol quitado')}
                    aria-label={`Quitar rol ${r.name}`}>
                    Quitar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </AsyncState>

        <label htmlFor="pos-role-add" className="form-label">Agregar rol</label>
        <div className="input-group">
          <select id="pos-role-add" className="form-select" value={roleId} onChange={(e) => setRoleId(e.target.value)}
            disabled={available.length === 0}>
            <option value="">{available.length === 0 ? 'No hay más roles' : 'Elegir…'}</option>
            {available.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.code})</option>)}
          </select>
          <button type="button" className="btn btn-primary" disabled={!roleId || busy}
            onClick={() => run(() => orgService.addPositionRole(position.id, roleId), 'Rol agregado')}>
            Agregar
          </button>
        </div>
        <div className="form-text">Los roles y sus permisos se definen en Roles y permisos.</div>
      </div>
    </Dialog>
  )
}
