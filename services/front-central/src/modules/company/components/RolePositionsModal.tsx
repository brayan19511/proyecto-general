import { useState } from 'react'
import Dialog from '../../../shared/components/Dialog'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as orgService from '../services/orgService'
import type { Position, PositionRole, Role } from '../types'

type RolePositionsModalProps = {
  role: Role
  positions: Position[] // activos
  rolesByPosition: Map<string, PositionRole[]>
  onClose: () => void
  onChanged: () => void
}

const byLabel = (a: Position, b: Position) => `${a.area.name} ${a.name}`.localeCompare(`${b.area.name} ${b.name}`, 'es')

// Puestos con un rol: lista de asignados (cada uno con "Desasignar") y un
// selector para asignarlo a otro puesto.
export default function RolePositionsModal({ role, positions, rolesByPosition, onClose, onChanged }: RolePositionsModalProps) {
  const [assigned, setAssigned] = useState(
    () => new Set(positions.filter((p) => rolesByPosition.get(p.id)?.some((r) => r.role_id === role.id)).map((p) => p.id)),
  )
  const [toAssign, setToAssign] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)

  const assignedList = positions.filter((p) => assigned.has(p.id)).sort(byLabel)
  const available = positions.filter((p) => !assigned.has(p.id)).sort(byLabel)
  const areas = [...new Set(available.map((p) => p.area.name))]

  const change = async (position: Position, assign: boolean) => {
    setBusyId(position.id)
    try {
      if (assign) await orgService.addPositionRole(position.id, role.id)
      else await orgService.removePositionRole(position.id, role.id)
      setAssigned((prev) => {
        const next = new Set(prev)
        if (assign) next.add(position.id)
        else next.delete(position.id)
        return next
      })
      setToAssign('')
      toast.success(assign ? `Rol asignado a ${position.name}` : `Rol desasignado de ${position.name}`)
      onChanged()
    } catch (err) {
      toast.error(errorMessage(err)) // 409 la empresa quedaría sin administradores, 403 delegación
    } finally {
      setBusyId(null)
    }
  }

  const busy = busyId !== null

  return (
    <Dialog open onClose={onClose} busy={busy} labelledBy="role-pos-title">
      <div className="card-header bg-transparent d-flex align-items-center">
        <div className="me-auto">
          <h2 id="role-pos-title" className="h5 mb-0">Puestos con el rol {role.name}</h2>
          <div className="small text-body-secondary">Quien tenga uno de estos puestos recibe los permisos del rol.</div>
        </div>
        <button type="button" className="btn-close" aria-label="Cerrar" onClick={onClose} disabled={busy} />
      </div>
      <div className="card-body">
        <h3 className="h6">Asignado a</h3>
        {assignedList.length === 0 ? (
          <p className="small text-body-secondary">Ningún puesto tiene este rol.</p>
        ) : (
          <ul className="list-group mb-4">
            {assignedList.map((p) => (
              <li key={p.id} className="list-group-item d-flex align-items-center gap-2">
                <div className="me-auto">
                  {p.name} <span className="small text-body-secondary">· {p.area.name}</span>
                </div>
                <button type="button" className="btn btn-sm btn-outline-danger" disabled={busy} onClick={() => change(p, false)}>
                  {busyId === p.id ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : 'Desasignar'}
                </button>
              </li>
            ))}
          </ul>
        )}

        <label htmlFor="role-pos-add" className="form-label h6">Asignar a otro puesto</label>
        <div className="input-group">
          <select id="role-pos-add" className="form-select" value={toAssign} disabled={available.length === 0 || busy}
            onChange={(e) => setToAssign(e.target.value)}>
            <option value="">{available.length === 0 ? 'Ya está en todos los puestos' : 'Elegir puesto…'}</option>
            {areas.map((area) => (
              <optgroup key={area} label={area}>
                {available.filter((p) => p.area.name === area).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </optgroup>
            ))}
          </select>
          <button type="button" className="btn btn-primary" disabled={!toAssign || busy}
            onClick={() => {
              const position = positions.find((p) => p.id === toAssign)
              if (position) change(position, true)
            }}>
            Asignar
          </button>
        </div>
      </div>
    </Dialog>
  )
}
