import { useState } from 'react'
import FormModal from '../../../shared/components/FormModal'
import { errorMessage } from '../../../shared/hooks/useApi'
import { toast } from '../../../shared/stores/toastStore'
import * as membersService from '../services/membersService'
import type { Member, Position } from '../types'

type AssignPositionModalProps = {
  member: Member
  positions: Position[] // activos
  onClose: () => void
  onAssigned: () => void
}

// Asigna un puesto a un miembro: así hereda los roles (y permisos) del puesto.
export default function AssignPositionModal({ member, positions, onClose, onAssigned }: AssignPositionModalProps) {
  // Solo los puestos que aún no tiene, agrupados por área.
  const available = positions.filter((p) => !member.positions.some((mp) => mp.id === p.id))
  const byArea = [...new Set(available.map((p) => p.area.name))].sort((a, b) => a.localeCompare(b, 'es'))
  const [positionId, setPositionId] = useState(available[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await membersService.assignPosition(member.id, positionId)
      toast.success('Puesto asignado')
      onAssigned()
      onClose()
    } catch (err) {
      setError(errorMessage(err)) // 403 sin permiso para delegar ese puesto, 409 ya lo tiene
    } finally {
      setBusy(false)
    }
  }

  return (
    <FormModal open title={`Asignar puesto a ${member.email}`} submitLabel="Asignar" busy={busy} error={error}
      canSubmit={positionId !== ''} onSubmit={submit} onClose={onClose}>
      {available.length === 0 ? (
        <p className="mb-0 text-body-secondary">No hay más puestos activos para asignar. Créalos en Áreas y puestos.</p>
      ) : (
        <>
          <label htmlFor="assign-position" className="form-label">Puesto</label>
          <select id="assign-position" className="form-select" value={positionId} onChange={(e) => setPositionId(e.target.value)}>
            {byArea.map((area) => (
              <optgroup key={area} label={area}>
                {available.filter((p) => p.area.name === area).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
                ))}
              </optgroup>
            ))}
          </select>
          <div className="form-text">El miembro recibe los roles del puesto en esta empresa.</div>
        </>
      )}
    </FormModal>
  )
}
